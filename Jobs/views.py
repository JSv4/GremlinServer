import logging
import mimetypes
import os, io, zipfile, sys
from zipfile import ZipFile
import json
from datetime import datetime

#simple-jwt views to override
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

from django.db.models import Count, Prefetch
from django.http import FileResponse, JsonResponse
from rest_framework import status
from rest_framework import viewsets, renderers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import ParseError
from rest_framework.parsers import FileUploadParser
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.schemas.openapi import AutoSchema
from rest_framework import mixins

from Jobs import serializers
from Jobs.tasks.task_helpers import transformStepInputs
from .models import Document, Job, Result, PythonScript, PipelineNode, Pipeline, TaskLogEntry, JobLogEntry, Edge
from .paginations import MediumResultsSetPagination, LargeResultsSetPagination, SmallResultsSetPagination
from .serializers import DocumentSerializer, JobSerializer, ResultSummarySerializer, PythonScriptSerializer, \
    PipelineSerializer, PipelineStepSerializer, PythonScriptSummarySerializer, LogSerializer, ResultSerializer, \
    PythonScriptSummarySerializer, PipelineSerializer, PipelineStepSerializer, \
    ProjectSerializer, Full_PipelineSerializer, Full_PipelineStepSerializer, EdgeSerializer
from .tasks.tasks import runJob

mimetypes.init()
mimetypes.knownfiles

# constants for logs to convert from # to text
# Enumerations for the task DB logger
LOG_LEVELS = {
    logging.NOTSET: "Not Set",
    logging.INFO: 'Info',
    logging.WARNING: 'Warning',
    logging.DEBUG: 'Debug',
    logging.ERROR: 'Error',
    logging.FATAL: 'Fatal',
}

# Write-Only Permissions on Script, Pipeline and PipelineStep for users with
# role = LAWYER
class WriteOnlyIfIsAdminOrEng(BasePermission):

    """
    Allows write access only to "ADMIN" or "LEGAL_ENG" users.
    """
    def has_permission(self, request, view):
        if request.user.role == "ADMIN" or request.user.role == "LEGAL_ENG":
            return True
        else:
            return request.method in ["GET", "HEAD", "OPTIONS"]

# From here: https://stackoverflow.com/questions/38697529/how-to-return-generated-file-download-with-django-rest-framework
class PassthroughRenderer(renderers.BaseRenderer):
    """
        Return data as-is. View should supply a Response.
    """
    media_type = ''
    format = ''
    permission_classes = [IsAuthenticated]

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return data


class ListInputModelMixin(object):

    def get_serializer(self, *args, **kwargs):
        """ if an array is passed, set serializer to many """
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super(ListInputModelMixin, self).get_serializer(*args, **kwargs)


class DocumentViewSet(viewsets.ModelViewSet):
    """
    retrieve:
    Get a given document object.

    list:
    List all of the documents.

    create:
    Create a new document object.
    """
    queryset = Document.objects.filter().prefetch_related('job').order_by('-name')
    filter_fields = ['id', 'name', 'extracted', 'job']

    pagination_class = MediumResultsSetPagination
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self, *args, **kwargs):
        #for legal engineers and lawyers, don't show them jobs or docs that don't belong to them.
        if self.request.user.role == "LEGAL_ENG"  or self.request.user.role == "LAWYER":
            return self.queryset.filter(owner=self.request.user.id)
        else:
            return self.queryset

    # One way to accept multiple objects via serializer:
    # See https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=isinstance(request.data, list))
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    # Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    # Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download(self, request, pk=None):

        """
            Download the document file linked to this document model.
        """

        document = Document.objects.filter(pk=pk)[0]

        # get an open file handle (I'm just using a file attached to the model for this example):
        file_handle = document.file.open()

        # send file
        filename, file_extension = os.path.splitext(document.file.name)
        mimetype = mimetypes.types_map[file_extension]
        response = FileResponse(file_handle)
        response['Content-Length'] = document.file.size
        response['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(document.file.name)
        response['Filename'] = os.path.basename(document.file.name)

        return response

    ##
    @action(methods=['get'], detail=True)
    def fullText(self, request, pk=None):
        try:
            rawText = Document.objects.filter(id=pk)[0].values('rawText')
            return JsonResponse({"rawText": rawText})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

# This


class LogViewSet(viewsets.ModelViewSet):
    queryset = TaskLogEntry.objects.select_related('owner', 'result').all().order_by('create_datetime')
    filter_fields = ['result']

    pagination_class = MediumResultsSetPagination
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated]


class JobLogViewSet(viewsets.ModelViewSet):
    queryset = JobLogEntry.objects.all().order_by('create_datetime')
    filter_fields = ['job']

    pagination_class = MediumResultsSetPagination
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated]


class ProjectSchema(AutoSchema):
    def get_operation(self, path, method):
        operation = super().get_operation(path, method)
        print("Operation for schema is:")
        print(operation)
        operation['parameters'].append({
            "name": "name",
            "in": "query",
            "required": True,
            "description": "What is the name of the job we'll create?",
            'schema': {'type': 'string'}
        })
        operation['parameters'].append({
            "name": "file",
            "in": "query",
            "required": True,
            "description": "Document file to analyze. Will be linked a job that will be linked to new job",
            'schema': {'type': 'file'}
        })
        operation['parameters'].append({
            "name": "pipeline",
            "in": "query",
            "required": True,
            "description": "Id of the processing pipeline to use.",
            'schema': {'type': 'integer'}
        })
        operation['parameters'].append({
            "name": "job_inputs",
            "in": "query",
            "required": False,
            "description": "Serialized JSON of the inputs for given job (if applicable).",
            'schema': {'type': 'string'}
        })
        operation['parameters'].append({
            "name": "callback",
            "in": "query",
            "required": False,
            "description": "The callback url to notify when the job is complete (a POST request will be made with multiparty form data containing resulting zip archive and serialized JSON data).",
            'schema': {'type': 'string'}
        })
        return operation


# See here: https://stackoverflow.com/questions/41104615/how-can-i-specify-the-parameter-for-post-requests-
# while-using-apiview-with-djang
class ProjectViewSet(GenericAPIView):
    """
        This is meant to simplify API usage of gremlin. The fields here are sufficient to a) create a new job and
        b) create a document and link it to the job. Once that's done, it's automatically started. On completion
        data is posted to the callback URL.

        post:
        Return the given user.

    """

    allowed_methods = ['post']
    serializer_class = ProjectSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        schema = ProjectSchema
        serializer = ProjectSerializer(data=self.request.data, context={'request': self.request})
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)


class JobViewSet(viewsets.ModelViewSet):

    queryset = Job.objects.annotate(num_docs=Count('document')).select_related('owner', 'pipeline').all().order_by(
        '-name')
    filter_fields = ['name', 'id', 'status', 'started', 'queued', 'finished', 'type']

    pagination_class = None
    serializer_class = JobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self, *args, **kwargs):
        # for legal engineers and lawyers, don't show them jobs or docs that don't belong to them.
        if self.request.user.role == "LEGAL_ENG" or self.request.user.role == "LAWYER":
            return self.queryset.filter(owner=self.request.user.id)
        else:
            return self.queryset

    # This action is a shortcut to create a doc and job obj at the same time and immediately run it. For a one-request
    # backend service workflow - e.g. make one request to gremlin to have a document analyzed.
    @action(methods=['put'], detail=False)
    def CreateJobAndProcessDoc(self, request):

        try:
            serializer = ProjectSerializer(data=request.data)
            if serializer.is_valid(raise_exception=True):
                return Response(serializer.data)
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # This action will run a job up through a certain step of its pipeline
    # e.g. if we called .../Job/1/RunToStep/2 that would run the job 1 pipeline to step index 2 (#3)
    # if the provided step_number is out of range, the whole pipeline will run.
    @action(methods=['get'], detail=True, url_name='RunToStep', url_path='RunToStep/(?P<step_number>[0-9]+)')
    def runToStep(self, request, pk=None, step_number=None):
        try:
            print(pk)
            print(step_number)
            runJob.delay(jobId=pk, endStep=int(step_number))
            return Response(status=status.HTTP_204_NO_CONTENT)

        except Exception as e:
            content = {'ERROR': e}
            return Response(content, status=status.HTTP_404_NOT_FOUND)

    # BE CAREFUL WITH THIS. DELETES ALL RESULTS FOR SELECTED JOB
    # Perhaps, once the UI works for this, have a method where you can reset only AFTER a specified pipeline step
    # Avoids having to reprocess an entire pipeline.
    @action(methods=['get'], detail=True)
    def reset_job(self, request, pk=None):
        try:
            deleted_ids = []
            results = Result.objects.filter(job=pk)
            for result in results:
                deleted_ids.append((result.id))
                result.delete()
            content = {'Deleted Results': deleted_ids}
            return Response(content, status=status.HTTP_200_OK)

        except Exception as e:
            content = {'ERROR': e}
            return Response(content, status=status.HTTP_404_NOT_FOUND)

    # Get the logs for this job... this will be gremlin-level sys logs describing the pipeline execution.
    # The user's logs for the scripts will not be included:
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def logs(self, request, pk=None):
        try:

            logs = JobLogEntry.objects.filter(job=pk)
            logTxt = ""
            stackTrace = ""
            error = False
            warn = False
            for log in reversed(logs):
                logTxt = logTxt + "\n({0}) {1} --- ".format(LOG_LEVELS[log.level], log.create_datetime) + log.msg
                if log.trace: stackTrace = stackTrace + "\n({0}) {1} --- \n\tMessage: {2}\n\nn\tTrace: {3}".format(
                    log.level, log.create_datetime, log.msg, log.trace)
            return JsonResponse({"log": logTxt, "stackTrace": stackTrace, "error": error, "warnings": warn})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    # Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download(self, request, pk=None):

        job = Job.objects.filter(pk=pk)[0]

        # get an open file handle (I'm just using a file attached to the model for this example):
        file_handle = job.file.open()

        # send file
        filename, file_extension = os.path.splitext(job.file.name)
        mimetype = mimetypes.types_map[file_extension]
        response = FileResponse(file_handle)
        response['Content-Length'] = job.file.size
        response['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(job.file.name)
        response['Filename'] = os.path.basename(job.file.name)

        return response

    @action(methods=['get'], detail=True)
    def TaskCount(self, request, pk=None):
        try:
            job = Job.objects.filter(pk=pk)[0]
            return JsonResponse({"data": {'id': pk, 'taskCount': job.task_count()}})
        except Exception as e:
            return JsonResponse({'data': {'id': pk, 'error': f"{e}"}})

    @action(methods=['get'], detail=True)
    def get_job_results_with_data(self, request, pk=None):
        try:
            results = Result.objects.filter(job=pk)
            serializer = ResultSerializer(results, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # Creates a JSON object of the results in the form that react-flowchart expects
    @action(methods=['get'], detail=True)
    def render_results_digraph(self, request, pk=None):

        try:
            job = Job.objects.prefetch_related('pipeline','result_set').get(pk=pk)
            pipeline = job.pipeline
            nodes = PipelineNode.objects.prefetch_related('out_edges', 'in_edges').filter(parent_pipeline=pipeline)
            edges = Edge.objects.filter(parent_pipeline=pipeline)
            results = job.result_set
            job_result = results.filter(job=job, type=Result.JOB)

            print(f"Results: {results}")
            print(f"Job Result: {job_result}")

            result_json = None
            if job_result.count() == 1:
                try:
                    result_json = job_result[0].id
                except:
                    pass

            digraph = {
                "offset": {
                    "x": 0,
                    "y": 0,
                },
                "type": ["RESULTS"],
                "scale": 1,
                "selected": {},
                "hovered": {},
                "result_id": result_json
            }
            renderedNodes = {}
            renderedEdges = {}

            for node in nodes:

                #Get node result
                node_result = results.filter(pipeline_node=node)
                print(f"Node result for node {node} is {node_result}")
                result = None
                if node_result.count() == 1:
                    try:
                        result = node_result[0].id
                    except:
                        pass

                ports = {}

                if node.type==PipelineNode.SCRIPT:
                    ports = {
                        "output": {
                            "id": 'output',
                            "type": 'output',
                        },
                        "input": {
                            "id": 'input',
                            "type": 'input',
                        },
                    }
                elif node.type==PipelineNode.ROOT_NODE:
                    ports = {
                        "output": {
                            "id": 'output',
                            "type": 'output',
                        },
                    }
                # TODO - handle more node types

                print("Try to render node")
                print(f"Node: {node}")
                renderedNode = {
                    "id": f"{node.id}",
                    "name": node.name,
                    "settings": node.step_settings,
                    "input_transform":node.input_transform,
                    "result_id": result,
                    "type": node.type,
                    "position": {
                        "x": node.x_coord,
                        "y": node.y_coord
                    },
                    "ports": ports
                }
                print(renderedNode)

                # Only need to handle instances where script is null (e.g. where the node is a root node and there's
                # no linked script because it's hard coded on the backend
                if node.type=="ROOT_NODE":
                    # If the default pre-processor has been overwritten... use linked script details
                    if node.script == None:
                        renderedNode["script"] = {
                            "id": -1,
                            "human_name": "Pre Processor",
                            "type": "RUN_ON_JOB_DOCS",
                            "supported_file_types": "",
                            "description": "Default pre-processor to ensure docx, doc and pdf files are extracted."
                        }
                    #otherwise... provide default values
                    else:
                        renderedNode["script"] = {
                            "id": node.script.id,
                            "human_name": node.script.human_name,
                            "type": node.script.type,
                            "supported_file_types": node.script.supported_file_types,
                            "description": node.script.description
                        }
                else:
                    renderedNode["script"] = {}

                renderedNodes[f"{node.id}"] = renderedNode

            for edge in edges:
                 renderedEdges[f"{edge.id}"] = {
                     "id": f"{edge.id}",
                     "from": {
                         "nodeId": f"{edge.start_node.id}",
                         "portId": "output"
                     },
                     "to": {
                         "nodeId": f"{edge.end_node.id}",
                         "portId": "input"
                     }
                 }

            digraph['nodes'] = renderedNodes
            digraph['links'] = renderedEdges

            return JsonResponse(digraph)

        except Exception as e:
            return Response(e,
                        status=status.HTTP_400_BAD_REQUEST)


class FileResultsViewSet(viewsets.ModelViewSet):
    queryset = Result.objects.select_related('owner', 'job', 'pipeline_node', 'doc').exclude(
        file='')
    filter_fields = ['id', 'job__id', 'start_time', 'stop_time']
    pagination_class = SmallResultsSetPagination
    serializer_class = ResultSummarySerializer
    permission_classes = [IsAuthenticated]


class ResultsViewSet(viewsets.ModelViewSet):
    queryset = Result.objects.select_related('owner', 'job', 'pipeline_node', 'doc').all().order_by('-job__id')
    filter_fields = ['id', 'job__id', 'start_time', 'stop_time']

    pagination_class = LargeResultsSetPagination
    serializer_class = ResultSummarySerializer
    permission_classes = [IsAuthenticated]

    # Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    # Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download(self, request, pk=None):

        documentResult = Result.objects.filter(pk=pk)[0]

        # get an open file handle (I'm just using a file attached to the model for this example):
        file_handle = documentResult.file.open()

        # send file
        filename, file_extension = os.path.splitext(documentResult.file.name)
        mimetype = mimetypes.types_map[file_extension]
        response = FileResponse(file_handle)
        response['Content-Length'] = documentResult.file.size
        response['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(documentResult.file.name)
        response['Filename'] = os.path.basename(documentResult.file.name)

        return response

    @action(methods=['get'], detail=True)
    def get_full_obj(self, request, pk=None):
        try:
            result = Result.objects.get(id=pk)
            serializer = ResultSerializer(result, many=False)
            return Response(serializer.data)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True)
    def get_output_data(self, request, pk=None):

        try:
            obj = Result.objects.get(id=pk)
            jsonObj = obj.output_data_value()

            return JsonResponse({"id": pk, "output_data": jsonObj})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True)
    def get_raw_input_data(self, request, pk=None):

        try:
            obj = Result.objects.get(id=pk)
            jsonObj = obj.raw_input_data_value()

            return JsonResponse({"id": pk, "raw_input_data": jsonObj})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True)
    def get_transformed_input_data(self, request, pk=None):

        try:
            obj = Result.objects.get(id=pk)
            jsonObj = obj.transformed_input_data_value()

            return JsonResponse({"id": pk, "transformed_input_data": jsonObj})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def logs(self, request, pk=None):
        try:

            logs = TaskLogEntry.objects.filter(result=pk)
            logTxt = ""
            stackTrace = ""
            error = False
            warn = False
            for log in reversed(logs):
                logTxt = logTxt + "\n({0}) {1} --- ".format(LOG_LEVELS[log.level], log.create_datetime) + log.msg
                if log.trace: stackTrace = stackTrace + "\n({0}) {1} --- \n\tMessage: {2}\n\nn\tTrace: {3}".format(
                    log.level, log.create_datetime, log.msg, log.trace)
            return JsonResponse({"log": logTxt, "stackTrace": stackTrace, "error": error, "warnings": warn})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


class PythonScriptViewSet(viewsets.ModelViewSet):
    queryset = PythonScript.objects.select_related('owner').all().order_by('-name')
    filter_fields = ['id', 'mode', 'type', 'human_name']

    pagination_class = None
    serializer_class = PythonScriptSummarySerializer
    permission_classes = [IsAuthenticated & WriteOnlyIfIsAdminOrEng]

    # I want to use different serializer for create vs other actions.
    # Based on the guidance here:https://stackoverflow.com/questions/22616973/django-rest-framework-use-different-serializers-in-the-same-modelviewset
    def get_serializer_class(self):

        if self.action == 'create':  # for create only, provided option to pass in script.
            return PythonScriptSerializer

        return PythonScriptSummarySerializer  # For list, update, delete, and all other actions

    # Rather than have every script list request cost enormous amounts of data, have client request script details on a
    # script-by-script basis
    @action(methods=['get'], detail=True)
    def GetDetails(self, request, pk=None):
        try:
            script = PythonScript.objects.get(id=pk)
            serializer = PythonScriptSerializer(script)
            return Response(serializer.data)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # Just as I'm trying to cut down on load times and data usage for scripts with loads with the "GetDetails"
    # action above, I similarly want to require updates to the meaty parts of a script (the script code),
    # etc, to go through a separate action.
    @action(methods=['put'], detail=True)
    def UpdateDetails(self, request, pk=None):
        try:
            serializer = PythonScriptSerializer(data=request.data)
            if serializer.is_valid(raise_exception=True):
                scriptData = serializer.data
                script = PythonScript.objects.get(id=pk)
                script.__dict__.update(scriptData)
                script.save()
                return Response(serializer.data)
            else:
                return Response(status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # Export the script as a gremlin archive
    @action(methods=['get'], detail=True)
    def exportArchive(self, request, pk=None):

        try:

            script = PythonScript.objects.get(id=pk)
            outputBytes = io.BytesIO()
            zipFile = ZipFile(outputBytes, mode='w', compression=zipfile.ZIP_DEFLATED)

            # write the logs if they exist
            if script.setup_log:
                zipFile.writestr(f"./logs/setupLog.log", script.setup_log)
            if script.installer_log:
                zipFile.writestr(f"./logs/pipLog.log", script.installer_log)

            # write the config files if they exist
            config = {}
            if script.description:
                config['description'] = script.description
            else:
                config['description'] = "No description..."

            if script.supported_file_types:
                config['supported_file_types'] = script.supported_file_types
            else:
                config['supported_file_types'] = ""

            if script.env_variables:
                config['env_variables'] = script.env_variables
            else:
                config['env_variables'] = ""

            if script.schema:
                config['schema'] = script.schema
            else:
                config['schema'] = ""

            if script.name:
                config['name'] = script.name
            else:
                config['name'] = "NO NAME"

            config['type'] = script.type

            # if the config object is not empty... write to a config.json file
            if config is not {}:
                zipFile.writestr(f"./config.json", json.dumps(config))

            # write the list of python packages as a pip file
            if script.required_packages:
                zipFile.writestr(f"./setup/requirements.txt", script.required_packages)

            # write the setup script as a .sh file (probably not quite right)
            if script.setup_script:
                zipFile.writestr(f"./setup/install.sh", script.setup_script)

            # write the script as a package
            if script.script:
                zipFile.writestr(f"./script/script.py", script.script)
                zipFile.writestr(f"./script/__init__.py", "EXPORTED BY GREMLIN")

            # Close the zip archive
            zipFile.close()
            outputBytes.seek(io.SEEK_SET)

            filename = f"{script.name}-gremlin_export.zip"
            response = FileResponse(outputBytes, as_attachment=True, filename=filename)
            response['filename']= filename
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


class UploadScriptViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [IsAuthenticated & WriteOnlyIfIsAdminOrEng]
    parser_classes = [FileUploadParser]

    def post(self, request, format=None):

        if not request.FILES['file']:
            print("Empty content!")
            raise ParseError("Empty content")

        print("Received a new PythonScript upload.")
        try:
            f = request.FILES['file'].open().read()

            with ZipFile(request.data['file'].open(), mode='r') as importZip:
                print("File successfully uploaded.")
                script = ""
                name = ""
                type = ""
                description = ""
                supported_file_types = ""
                env_variables = ""
                schema = ""
                requirements = ""
                setup_script = ""

                print(f"Received zip file contents: {importZip.namelist()}")

                if not "./script/script.py" in importZip.namelist():
                    print("No script @ ./script/script.py")
                    raise ParseError("No /script/script.py")
                else:
                    print("Found script @ ./script/script.py")
                    with importZip.open("./script/script.py") as myfile:
                        script = myfile.read().decode('UTF-8')
                print(f"Loaded script: {script}")

                if not "./config.json" in importZip.namelist():
                    print("No config file @ ./config.json")
                    raise ParseError("No ./config.json config file")
                else:
                    with importZip.open("./config.json") as configFile:

                        config_text = configFile.read().decode('UTF-8')
                        print(f"Loaded config file @ ./config.json: {config_text}")
                        config = json.loads(config_text)
                        name = config['name']
                        type = config['type']
                        description = config['description']
                        supported_file_types = config['supported_file_types']
                        env_variables = config['env_variables']

                print(f"Parsed config file = {config}")

                if "./setup/requirements.txt" in importZip.namelist():
                    print("Detected requirements file @ ./setup/requirements.txt")
                    with importZip.open("./setup/requirements.txt") as requirementsFile:
                        requirements = requirementsFile.read().decode('UTF-8')
                print(f"Requirements file extracted: {requirements}")

                if "./setup/install.sh" in importZip.namelist():
                    print("Detected install commands @ ./setup/install.sh")
                    with importZip.open("./setup/install.sh") as setupFile:
                        setup_script = setupFile.read().decode('UTF-8')
                print(f"Importing setup_script: {setup_script}")

                # We do NOT import logs in case you're looking for those imports... log are exported from live scripts
                # but you'll get a new setup log when you import a new script.

                # Create a script
                script = PythonScript.objects.create(
                    script=script,
                    name=name,
                    human_name=name.replace(" ","_"),
                    description=description,
                    supported_file_types=supported_file_types,
                    env_variables=env_variables,
                    schema=schema,
                    required_packages=requirements,
                    setup_script=setup_script,
                    type=type,
                )
                script.save()

                print("Script imported and saved.")

                serializer = PythonScriptSerializer(script)
                print(f"Should return: {serializer.data}")

                response = JsonResponse(serializer.data)
                return response

        except Exception as e:
            print("Exception encountered: ")
            print(e)
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


class PipelineViewSet(viewsets.ModelViewSet):
    # You can sort the nested objects if you want when you prefetch them. You can also presort them at serialization time
    # Went with the former approach. See more here: https://stackoverflow.com/questions/48247490/django-rest-framework-nested-serializer-order/48249910
    queryset = Pipeline.objects.prefetch_related('owner', Prefetch('pipelinenodes',
                queryset=PipelineNode.objects.order_by('-step_number'))).all().order_by('-name')
    filter_fields = ['id', 'name', 'production']

    pagination_class = None
    serializer_class = Full_PipelineSerializer
    permission_classes = [IsAuthenticated & WriteOnlyIfIsAdminOrEng]

    # Clears any existing test jobs and creates a new one.
    @action(methods=['post'], detail=False)
    def delete_multiple(self, request):

        try:
            status = "ok"
            pipelines = Pipeline.objects.filter(pk__in=request.data['ids'])
            if pipelines.count() == 0:
                status = "No matching objects."
            deleted = list(map(lambda x: x.id, pipelines))
            pipelines.delete()
            return JsonResponse({"status": status, "deleted": deleted})

        except Exception as e:
            return Response(e,
                        status=status.HTTP_400_BAD_REQUEST)

    # Clears any existing test jobs and creates a new one.
    @action(methods=['get'], detail=True)
    def get_full_pipeline(self, request, pk=None):

        try:

            pipeline = Pipeline.objects.prefetch_related('pipelinenodes','owner').get(id=pk)
            serializer = Full_PipelineSerializer(pipeline, many=False)
            return Response(serializer.data)

        except Exception as e:
            return Response(e,
                        status=status.HTTP_400_BAD_REQUEST)

    # Creates a JSON object of the form that react-flowchart expects
    @action(methods=['get'], detail=True)
    def render_digraph(self, request, pk=None):

        try:
            nodes = PipelineNode.objects.prefetch_related('out_edges', 'in_edges').filter(parent_pipeline__id=pk)
            edges = Edge.objects.filter(parent_pipeline__id=pk)
            pipeline = Pipeline.objects.get(pk=pk)

            digraph = {
                "offset": {
                    "x": pipeline.x_offset,
                    "y": pipeline.y_offset,
                },
                "type": ["PIPELINE"],
                "scale": pipeline.scale,
                "selected": {},
                "hovered": {},
            }
            renderedNodes = {}
            renderedEdges = {}

            for node in nodes:

                ports = {}

                if node.type==PipelineNode.SCRIPT:
                    ports = {
                        "output": {
                            "id": 'output',
                            "type": 'output',
                        },
                        "input": {
                            "id": 'input',
                            "type": 'input',
                        },
                    }
                elif node.type==PipelineNode.ROOT_NODE:
                    ports = {
                        "output": {
                            "id": 'output',
                            "type": 'output',
                        },
                    }
                # TODO - handle more node types

                print("Try to render node")
                print(f"Node: {node}")
                renderedNode = {
                    "id": f"{node.id}",
                    "name": node.name,
                    "settings": node.step_settings,
                    "input_transform":node.input_transform,
                    "type": node.type,
                    "position": {
                        "x": node.x_coord,
                        "y": node.y_coord
                    },
                    "ports": ports
                }
                print(renderedNode)

                # Only need to handle instances where script is null (e.g. where the node is a root node and there's
                # no linked script because it's hard coded on the backend
                if node.type=="ROOT_NODE":
                    # If the default pre-processor has been overwritten... use linked script details
                    if node.script == None:
                        renderedNode["script"] = {
                            "id": -1,
                            "human_name": "Pre Processor",
                            "type": "RUN_ON_JOB_DOCS",
                            "supported_file_types": "",
                            "description": "Default pre-processor to ensure docx, doc and pdf files are extracted."
                        }
                    #otherwise... provide default values
                    else:
                        renderedNode["script"] = {
                            "id": node.script.id,
                            "human_name": node.script.human_name,
                            "type": node.script.type,
                            "supported_file_types": node.script.supported_file_types,
                            "description": node.script.description
                        }
                else:
                    renderedNode["script"] = {}

                renderedNodes[f"{node.id}"] = renderedNode

            for edge in edges:
                 renderedEdges[f"{edge.id}"] = {
                     "id": f"{edge.id}",
                     "from": {
                         "nodeId": f"{edge.start_node.id}",
                         "portId": "output"
                     },
                     "to": {
                         "nodeId": f"{edge.end_node.id}",
                         "portId": "input"
                     }
                 }

            digraph['nodes'] = renderedNodes
            digraph['links'] = renderedEdges

            return JsonResponse(digraph)

        except Exception as e:
            return Response(e,
                        status=status.HTTP_400_BAD_REQUEST)

# This mixin lets DRF inbound serialized determine if a list or single object is being passed in... IF, it's a list,
# will instantiate any serializer with the many=True option, allowing for bulk updates and creates.
# https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
# the actual answer in that SO doesn't work right as it can't handle both lists and objects.
class PipelineStepViewSet(ListInputModelMixin, viewsets.ModelViewSet):
    queryset = PipelineNode.objects.all().order_by('-name')
    filter_fields = ['id', 'name', 'parent_pipeline']

    pagination_class = None
    serializer_class = Full_PipelineStepSerializer
    permission_classes = [IsAuthenticated & WriteOnlyIfIsAdminOrEng]

    @action(methods=['get'], detail=True, url_name='JobLogs', url_path='JobLogs/(?P<job_id>[0-9]+)')
    def logs(self, request, pk=None, job_id=None):
        try:
            results = Result.objects.filter(pipeline_node=pk, job=job_id)
            logText = ""

            for count, result in enumerate(results):
                logText = logText + "\n--- Result {0} of {1}: {2}\n".format(count + 1, len(results), result.name)
                logs = TaskLogEntry.objects.filter(result=result.pk)
                for log in reversed(logs):
                    logText = logText + "\n\t({0}) {1} --- ".format(LOG_LEVELS[log.level],
                                                                    log.create_datetime) + log.msg

            return JsonResponse({"log": logText, "error": ""})

        except Exception as e:
            return JsonResponse({"log": "No logs", "error": "ERROR: {0}".format(e)})

    @action(methods=['put'], detail=False)
    def test_transform_script(self, request):
        try:
            input_data = request.data['input_data']
            input_transform = request.data['input_transform']
            return_data = {"error": "No errors."}

            if input_transform:
                return_data['output_data'] = transformStepInputs(input_transform, input_data)
            else:
                return_data['output_data'] = input_data

            return JsonResponse(return_data)

        except Exception as e:
            return JsonResponse({"output_data": {}, "error": "ERROR: {0}".format(e)})

    @action(methods=['put'], detail=True)
    def test_step_transform_script(self, request, pk=None):
        try:
            step = PipelineNode.objects.get(id=pk)
            input_data = request.data['input_data']
            return_data = {"error": "No errors."}

            if step.input_transform:
                return_data['output_data'] = transformStepInputs(step.input_transform, input_data)
            else:
                return_data['output_data'] = input_data

            return JsonResponse(return_data)

        except Exception as e:
            return JsonResponse({"output_data": {}, "error": "ERROR: {0}".format(e)})


class EdgeViewSet(ListInputModelMixin, viewsets.ModelViewSet):
    queryset = Edge.objects.all().order_by('id')
    filter_fields = ['id', 'start_node__id', 'end_node__id']

    pagination_class = None
    serializer_class = EdgeSerializer
    permission_classes = [IsAuthenticated & WriteOnlyIfIsAdminOrEng]
