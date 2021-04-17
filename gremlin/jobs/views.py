"""
Gremlin - The open source legal engineering platform
Copyright (C) 2020-2021 John Scrudato IV ("JSIV")

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/
"""

# Python Modules
import logging
import tempfile
import mimetypes
import os, io, zipfile, sys
from zipfile import ZipFile
import json
import base64

# YAML Stuff
from ruamel.yaml import YAML

# Django Stuff
from django.http.response import HttpResponse
from django.db.models import Count, Prefetch
from django.http import FileResponse, JsonResponse
from django.conf import settings
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile

# Django Rest Framework Stuff
from rest_framework import status
from rest_framework import viewsets, renderers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import ParseError
from rest_framework.parsers import FileUploadParser, MultiPartParser
from rest_framework.views import APIView
from rest_framework.generics import GenericAPIView
from rest_framework.schemas.openapi import AutoSchema
from rest_framework.renderers import JSONRenderer

# Gremlin jobs Models and Serializers
from gremlin.jobs.ImportExportUtils import exportScriptYAMLObj, exportPipelineNodeToYAMLObj, \
    exportPipelineEdgeToYAMLObj, exportPipelineToYAMLObj, importPipelineFromYAML, exportPipelineToZip, \
    importPipelineFromZip
from gremlin.jobs.tasks.task_helpers import transformStepInputs
from .models import Document, Job, Result, PythonScript, PipelineNode, Pipeline, TaskLogEntry, JobLogEntry, Edge, \
    ScriptDataFile
from .paginations import MediumResultsSetPagination, SmallResultsSetPagination
from .serializers import DocumentSerializer, JobSerializer, ResultSummarySerializer, PythonScriptSerializer, \
    PythonScriptNestedDataSerializer, LogSerializer, ResultSerializer, PythonScriptSummarySerializer, \
    PipelineSerializer, ProjectSerializer, JobCreateSerializer, Full_PipelineStepSerializer, EdgeSerializer, \
    PipelineSummarySerializer, PipelineDigraphSerializer, ScriptDataFileSerializer
from .tasks.tasks import runJobToNode

# Gremlin User Models and Serializers
from gremlin.users.models import User

# Shared utility classes like filters
from gremlin.utils.filters import PipelineFilter, JobFilter

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
class WriteOnlyIfNotAdminOrEng(BasePermission):
    """
    Allows write access only to "ADMIN" or "LEGAL_ENG" users.
    """

    def has_permission(self, request, view):
        if request.user.role == "ADMIN" or request.user.role == "LEGAL_ENG":
            return True
        else:
            return request.method in ["GET", "HEAD", "OPTIONS"]


# Permission class only gives access to admin or legal engineers
class AdminOrLegalEngAccessOnly(BasePermission):
    """
    Allows access only to "ADMIN" users.
    """

    def has_permission(self, request, view):
        return request.user.role == User.LEGAL_ENG or request.user.role == User.ADMIN


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

class ZipPassthroughRenderer(renderers.BaseRenderer):
    """
        Return data as-is. View should supply a Response.
    """
    media_type = ''
    format = ''
    permission_classes = [IsAuthenticated]

    def render(self, data, accepted_media_type="application/zip", renderer_context=None):
        return data

class ListInputModelMixin(object):

    def get_serializer(self, *args, **kwargs):
        """ if an array is passed, set serializer to many """
        if isinstance(kwargs.get('data', {}), list):
            kwargs['many'] = True
        return super(ListInputModelMixin, self).get_serializer(*args, **kwargs)


class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.filter().prefetch_related('job').order_by('-name')
    filter_fields = ['id', 'name', 'extracted', 'job']

    pagination_class = MediumResultsSetPagination
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_queryset(self, *args, **kwargs):
        # for legal engineers and lawyers, don't show them jobs or docs that don't belong to them.
        if self.request.user.role == "LEGAL_ENG" or self.request.user.role == "LAWYER":
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


class LogViewSet(viewsets.ModelViewSet):
    queryset = TaskLogEntry.objects.select_related('owner', 'result').all().order_by('create_datetime')
    filter_fields = ['result']

    pagination_class = MediumResultsSetPagination
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class JobLogViewSet(viewsets.ModelViewSet):
    queryset = JobLogEntry.objects.all().order_by('create_datetime')
    filter_fields = ['job']

    pagination_class = MediumResultsSetPagination
    serializer_class = LogSerializer
    permission_classes = [IsAuthenticated]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


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
    queryset = Job.objects.annotate(num_docs=Count('document')).select_related('owner', 'pipeline').all()
    pagination_class = MediumResultsSetPagination
    permission_classes = [IsAuthenticated]
    filterset_class = JobFilter

    # mapping serializer into the action
    serializer_classes = {
        'list': JobSerializer,
        'retrieve': JobSerializer,
        'create': JobCreateSerializer,
        'update': JobCreateSerializer,
        'partial_update': JobCreateSerializer,
        'destroy': JobCreateSerializer
    }
    default_serializer_class = JobSerializer  # Your default serializer

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.default_serializer_class)

    def get_queryset(self, *args, **kwargs):
        # for legal engineers and lawyers, don't show them jobs or docs that don't belong to them.
        if self.request.user.role == "LEGAL_ENG" or self.request.user.role == "LAWYER":
            return self.queryset.filter(owner=self.request.user.id).order_by('-created')
        else:
            return self.queryset.order_by('-created')

    # Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    # Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download(self, request, pk=None):

        job = Job.objects.filter(pk=pk)[0]

        # get an open file handle (I'm just using a file attached to the model for this example):
        file_handle = job.file.open()

        # send file
        filename, file_extension = os.path.splitext(job.file.name)
        response = FileResponse(file_handle)
        response['Content-Length'] = job.file.size
        response['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(job.file.name)
        response['Filename'] = os.path.basename(job.file.name)

        return response

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
    @action(methods=['get'], detail=True, url_name='RunToStep', url_path='RunToNode/(?P<endNodeId>[0-9]+)')
    def runToStep(self, request, pk=None, endNodeId=None):
        try:
            print(pk)
            print(endNodeId)
            runJobToNode.delay(jobId=pk, endNodeId=int(endNodeId))
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

    @action(methods=['get'], detail=True)
    def TaskCount(self, request, pk=None):
        try:
            job = Job.objects.filter(pk=pk)[0]
            return JsonResponse({"data": {'id': pk, 'taskCount': job.task_count()}})
        except Exception as e:
            return JsonResponse({'data': {'id': pk, 'error': f"{e}"}})

    @action(methods=['get'], detail=True)
    def summary_results(self, request, pk=None):
        try:
            results = Result.objects.filter(job=pk)
            serializer = ResultSummarySerializer(results, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True)
    def full_results(self, request, pk=None):
        try:
            results = Result.objects.filter(job=pk)
            serializer = ResultSerializer(results, many=True)
            return Response(serializer.data)
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

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class ResultsViewSet(viewsets.ModelViewSet):
    queryset = Result.objects.select_related('owner', 'job', 'pipeline_node', 'doc').all().order_by('-job__id')
    filter_fields = ['id', 'job__id', 'start_time', 'stop_time', 'pipeline_node__id']

    pagination_class = None
    serializer_class = ResultSummarySerializer
    permission_classes = [IsAuthenticated]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    # Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download(self, request, pk=None):

        targetResult = Result.objects.filter(pk=pk)[0]

        # get an open file handle (I'm just using a file attached to the model for this example):
        file_handle = targetResult.file.open()

        # send file
        filename, file_extension = os.path.splitext(targetResult.file.name)
        mimetype = mimetypes.types_map[file_extension]
        response = FileResponse(file_handle)
        response['Content-Length'] = targetResult.file.size
        response['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(targetResult.file.name)
        response['Filename'] = os.path.basename(targetResult.file.name)

        return response

    @action(methods=['put'], detail=True)
    def test_transform_script(self, request, pk=None):

        try:
            result = Result.objects.get(pk=pk)

            try:
                input_data = json.loads(result.raw_input_data)
            except:
                input_data = {}

            input_transform = request.data['input_transform']
            return_data = {}

            if input_transform:
                return_data['output_data'] = transformStepInputs(input_transform, input_data)
            else:
                return_data['output_data'] = input_data

            return JsonResponse(return_data)

        except Exception as e:
            return JsonResponse({"output_data": {}, "error": "ERROR: {0}".format(e)})

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
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

        # I want to use different serializer for create vs other actions.

    # Based on the guidance here:https://stackoverflow.com/questions/22616973/django-rest-framework-use-different-serializers-in-the-same-modelviewset
    def get_serializer_class(self):

        if self.action in ['list', 'delete']:
            return PythonScriptSummarySerializer
        elif self.action == 'retrieve':
            # retrieve we want to use a nested serializer for data file
            return PythonScriptNestedDataSerializer
        else:  # for update serializers
            return PythonScriptSerializer


    # Export script as YAML
    @action(methods=['get'], detail=True)
    def ExportToYAML(self, request, pk=None):
        try:
            filename = f"Script-{pk}.yaml"
            myYaml = io.StringIO()
            yaml = YAML()
            yaml.preserve_quotes = False
            yaml.dump(exportScriptYAMLObj(pk), myYaml)
            response = HttpResponse(myYaml.getvalue(), content_type='text/plain', status=status.HTTP_200_OK)
            response['Content-Disposition'] = 'attachment; filename={0}'.format(filename)
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # Rather than have every script list request cost enormous amounts of data, have client request script details on a
    # script-by-script basis
    @action(methods=['get'], detail=True)
    def GetDetails(self, request, pk=None):
        try:
            script = PythonScript.objects.get(id=pk)
            serializer = PythonScriptNestedDataSerializer(script)
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
            print(f"UpdateDetails for script {pk}")
            serializer = PythonScriptSerializer(data=request.data)
            print(f"Serializer: {serializer}")
            if serializer.is_valid(raise_exception=True):
                print("Serializer is valid")
                scriptData = serializer.validated_data
                print(f"ScriptData is: {scriptData}")
                script = PythonScript.objects.get(id=pk)
                print("Try to update script")
                script.__dict__.update(scriptData)
                script.save()
                print("Done")
                return Response(PythonScriptSerializer(script).data)
            else:
                print("Serializer is invalid...")
                return Response(status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            print(f"Error updating script: {e}")
            return Response(f"{e}",
                            status=status.HTTP_400_BAD_REQUEST)

    # Export the script as a gremlin archive
    @action(methods=['get'], detail=True)
    def exportArchive(self, request, pk=None):

        try:

            script = PythonScript.objects.get(id=pk)

            outputBytes = io.BytesIO()
            zipFile = ZipFile(outputBytes, mode='w', compression=zipfile.ZIP_DEFLATED)

            if script.data_file and script.data_file.data_file:

                try:
                    # Check storage type so we load proper format
                    usingS3 = (
                            settings.DEFAULT_FILE_STORAGE == "gremlin.utils.storages.MediaRootS3Boto3Storage")

                    # THe precise field with the valid filename / path depends on the storage adapter, so handle accordingly
                    if usingS3:
                        filename = script.data_file.data_file.name

                    else:
                        filename = script.data_file.data_file.path

                    # Load the file object from Django storage backend, save it to local /tmp dir
                    data_file_bytes = default_storage.open(filename, mode='rb')
                    print(f"File loaded from DB: {filename}")

                    serverZip = zipfile.ZipFile(data_file_bytes)

                    print(f"Zip obj loaded from bytes {serverZip}")

                    with tempfile.TemporaryDirectory() as tmpdirname:
                        print(f"Create {tmpdirname} to extract all to")
                        serverZip.extractall(tmpdirname)
                        print("Extract complete")

                        for root, _, filenames in os.walk(tmpdirname):
                            for root_name in filenames:
                                print(f"Handle zip of {root_name}")
                                name = os.path.join(root, root_name)
                                name = os.path.normpath(name)
                                with open(name, mode='rb') as extracted_file:
                                    zipFile.writestr(f'/data/{root_name}', extracted_file.read())

                    serverZip.close()

                except Exception as e:
                    print(f"Error trying to export zip: {e}")

            # write the logs if they exist
            if script.setup_log:
                zipFile.writestr(f"/logs/setupLog.log", script.setup_log)
            if script.installer_log:
                zipFile.writestr(f"/logs/pipLog.log", script.installer_log)

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
                zipFile.writestr(f"/config.json", json.dumps(config))

            # write the list of python packages as a pip file
            if script.required_packages:
                zipFile.writestr(f"/setup/requirements.txt", script.required_packages)

            # write the setup script as a .sh file (probably not quite right)
            if script.setup_script:
                zipFile.writestr(f"/setup/install.sh", script.setup_script)

            # write the script as a package
            if script.script:
                zipFile.writestr(f"/script/script.py", script.script)
                zipFile.writestr(f"/script/__init__.py", "EXPORTED BY GREMLIN")

            # Close the zip archive
            zipFile.close()
            outputBytes.seek(io.SEEK_SET)

            filename = f"{script.name}-gremlin_export.zip"
            response = FileResponse(outputBytes, as_attachment=True, filename=filename)
            response['filename'] = filename
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def delete_data(self, request, pk=None):

        script = PythonScript.objects.prefetch_related('data_file').get(pk=pk)

        if script.data_file:
            data_file_ref = script.data_file
            data_file_ref.delete()
            script.data_file=None
            script.save()

        serializer = PythonScriptSummarySerializer(script)
        response = JsonResponse(serializer.data)
        return response


    # Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    # Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download_data(self, request, pk=None):

        """
            Download the data file linked to this script.
        """

        script = PythonScript.objects.prefetch_related('data_file').get(pk=pk)
        data_file = script.data_file

        # get an open file handle:
        file_handle = data_file.data_file.open()

        # send file
        filename, file_extension = os.path.splitext(data_file.data_file.name)
        mimetype = mimetypes.types_map[file_extension]
        response = FileResponse(file_handle)
        response['Content-Length'] = data_file.data_file.size
        response['Content-Disposition'] = 'attachment; filename="%s"' % os.path.basename(data_file.data_file.name)
        response['Filename'] = os.path.basename(data_file.data_file.name)

        return response

    @action(methods=['post'], detail=True, renderer_classes=(JSONRenderer,))
    def upload_data(self, request, pk=None):

        if not request.FILES['data_file']:
            print("Empty content!")
            raise ParseError("Empty content")

        try:

            print(f"Got new data file for script ID #{pk}: {request.FILES['data_file'].name}")

            script = PythonScript.objects.get(pk=pk)

            manifest = ""
            data_file_bytes = io.BytesIO(request.FILES['data_file'] .read())

            print("Request file read")

            importZip = zipfile.ZipFile(data_file_bytes)
            for filename in importZip.namelist():
                print(f"Handle import filename {filename}")
                manifest = manifest + f"\n{filename}" if manifest else filename
            importZip.close()

            print("Manifest built")

            zip_file = ContentFile(data_file_bytes.getvalue())

            # If there's already a data object associate with script, update it. Otherwise, create a new one.
            if script.data_file:
                db_data_obj = script.data_file
            else:
                db_data_obj = ScriptDataFile.objects.create()

            db_data_obj.manifest = manifest
            db_data_obj.data_file.save("data.zip", zip_file)
            db_data_obj.save()

            script.data_file = db_data_obj
            script.save()

            serializer = PythonScriptSerializer(script)
            response = JsonResponse(serializer.data)
            response.accepted_media_type="application/zip"

            return response

        except Exception as e:
            print("Exception encountered: ")
            print(e)
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


class UploadPipelineZipViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]
    parser_classes = [MultiPartParser]

    def post(self, request, format=None):

        if not request.FILES['file']:
            print("No file present")
            raise ParseError("You haven't provided a file")

        try:

            print(f"Got new pipeline file: {request.FILES['file'].name}")

            parent_pipeline = importPipelineFromZip(request.FILES['file'].read(), request.user)
            serializer = PipelineSerializer(parent_pipeline)

            print(f"Should return: {serializer.data}")

            response = JsonResponse(serializer.data)

            return response

        except Exception as e:
            print("Exception encountered importing Pipeline Zip: ")
            print(e)
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


# class UploadPipelineViewSet(APIView):
#     allowed_methods = ['post']
#     permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]
#     parser_classes = [MultiPartParser]
#
#     def post(self, request, format=None):
#
#         if not request.FILES['file']:
#             print("Empty content!")
#             raise ParseError("Empty content")
#
#         try:
#
#             print(f"Got new pipeline file: {request.FILES['file'].name}")
#             print(request.data)
#
#             yamlString = request.FILES['file'].read()
#             print("Yaml string toooo:")
#             print(yamlString)
#             parent_pipeline = importPipelineFromYAML(yamlString, request.user)
#             serializer = PipelineSerializer(parent_pipeline)
#
#             print(f"Should return: {serializer.data}")
#
#             response = JsonResponse(serializer.data)
#             return response
#
#         except Exception as e:
#             print("Exception encountered: ")
#             print(e)
#             return Response(e,
#                             status=status.HTTP_400_BAD_REQUEST)
#

class UploadScriptViewSet(APIView):
    allowed_methods = ['post']
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]
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
                schema = ""
                requirements = ""
                setup_script = ""
                db_data_obj = None

                print(f"Received zip file contents: {importZip.namelist()}")

                if "/script/script.py" in importZip.namelist():
                    print("Found script @ /script/script.py")
                    with importZip.open("/script/script.py") as myfile:
                        script = myfile.read().decode('UTF-8')

                elif "script/script.py" in importZip.namelist():
                    print("Found script @ script/script.py")
                    with importZip.open("script/script.py") as myfile:
                        script = myfile.read().decode('UTF-8')

                else:
                    print("No script @/script/script.py")
                    raise ParseError("No /script/script.py")

                print(f"Loaded script: {script}")

                if "/config.json" in importZip.namelist():
                    config_path = "/config.json"

                elif "config.json":
                    config_path = "config.json"

                else:
                    print("No config file @ ./config.json")
                    raise ParseError("No /config.json config file")

                with importZip.open(config_path) as configFile:
                    config_text = configFile.read().decode('UTF-8')
                    print(f"Loaded config file @ ./config.json: {config_text}")
                    config = json.loads(config_text)
                    name = config['name']
                    type = config['type']
                    description = config['description']
                    supported_file_types = config['supported_file_types']
                    env_variables = config['env_variables']
                print(f"Parsed config file = {config}")

                if "/setup/requirements.txt" in importZip.namelist():
                    print("Detected requirements file @ /setup/requirements.txt")
                    with importZip.open("/setup/requirements.txt") as requirementsFile:
                        requirements = requirementsFile.read().decode('UTF-8')
                elif "setup/requirements.txt" in importZip.namelist():
                    print("Detected requirements file @ setup/requirements.txt")
                    with importZip.open("setup/requirements.txt") as requirementsFile:
                        requirements = requirementsFile.read().decode('UTF-8')
                print(f"Requirements file extracted: {requirements}")

                if "/setup/install.sh" in importZip.namelist():
                    print("Detected install commands @ ./setup/install.sh")
                    with importZip.open("/setup/install.sh") as setupFile:
                        setup_script = setupFile.read().decode('UTF-8')
                elif "setup/install.sh" in importZip.namelist():
                    print("Detected install commands @ setup/install.sh")
                    with importZip.open("setup/install.sh") as setupFile:
                        setup_script = setupFile.read().decode('UTF-8')
                print(f"Importing setup_script: {setup_script}")

                # look to see if there's anything in the data directory and, if so, zip and add to database
                hasFiles = False
                manifest = ""
                dataZipBytes = io.BytesIO()

                with zipfile.ZipFile(dataZipBytes, mode='w', compression=zipfile.ZIP_DEFLATED) as dataZipObj:

                    for filename in [name for name in importZip.namelist() if name.startswith('/data/')]:
                        print(f"Handle filename {filename}")
                        hasFiles = True
                        dataZipObj.writestr(os.path.basename(filename), importZip.open(filename).read())
                        manifest = manifest + f"\n{filename}" if manifest else filename

                    for filename in [name for name in importZip.namelist() if name.startswith('data/')]:
                        print(f"Handle filename {filename}")
                        hasFiles = True
                        dataZipObj.writestr(os.path.basename(filename), importZip.open(filename).read())
                        manifest = manifest + f"\n{filename}" if manifest else filename

                if hasFiles:

                    print("Import has data files...")

                    with ContentFile(dataZipBytes.getvalue()) as zipFile:

                        db_data_obj = ScriptDataFile.objects.create(manifest=manifest)
                        db_data_obj.data_file.save("data.zip", zipFile)
                        db_data_obj.save()

                else:
                    print("No data dir")

                # We do NOT import logs in case you're looking for those imports... log are exported from live scripts
                # but you'll get a new setup log when you import a new script.

                # Create a script - if there is a db_data_obj, add relationship to new Script Model
                if db_data_obj:
                    script = PythonScript.objects.create(
                        owner=request.user,
                        script=script,
                        name=name,
                        human_name=name.replace(" ", "_"),
                        description=description,
                        supported_file_types=supported_file_types,
                        env_variables=env_variables,
                        schema=schema,
                        required_packages=requirements,
                        setup_script=setup_script,
                        type=type,
                        data_file=db_data_obj
                    )
                    script.save()
                else:
                    script = PythonScript.objects.create(
                        owner=request.user,
                        script=script,
                        name=name,
                        human_name=name.replace(" ", "_"),
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

class ScriptDataFileViewset(viewsets.ModelViewSet):

    serializer_class =ScriptDataFileSerializer
    queryset = ScriptDataFile.objects.all().order_by('modified')
    filter_fields=['uuid']
    pagination_class = SmallResultsSetPagination
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]

class PipelineSummaryViewSet(viewsets.ModelViewSet):
    serializer_class = PipelineSummarySerializer
    queryset = Pipeline.objects.prefetch_related('owner', Prefetch('pipelinenodes',
                                                                   queryset=PipelineNode.objects.order_by(
                                                                       '-step_number'))).all().order_by('-name')
    filter_fields = ['id', 'name', 'production']

    pagination_class = SmallResultsSetPagination
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]
    filterset_class = PipelineFilter

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)


class PipelineViewSet(viewsets.ModelViewSet):
    # You can sort the nested objects if you want when you prefetch them. You can also presort them at serialization time
    # Went with the former approach. See more here: https://stackoverflow.com/questions/48247490/django-rest-framework-nested-serializer-order/48249910
    queryset = Pipeline.objects.prefetch_related('owner').all().order_by('-name')
    filter_fields = ['id', 'name', 'production']

    pagination_class = SmallResultsSetPagination
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]
    filterset_class = PipelineFilter
    serializer_class = PipelineSummarySerializer

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # Clears any existing test jobs and creates a new one.
    # Clears any existing test jobs and creates a new one.
    @action(methods=['get'], detail=True)
    def get_test_job(self, request, pk=None):

        # try:
        test_jobs = Job.objects.filter(type='TEST')
        if test_jobs:
            for job in test_jobs:
                job.delete()

        pipeline = Pipeline.objects.get(id=pk)
        test_job = Job.objects.create(
            owner=request.user,
            name="TEST JOB",
            type="TEST",
            pipeline=pipeline
        )

        serializer = JobSerializer(test_job, many=False)
        return Response(serializer.data)

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

    @action(methods=['get'], detail=True)
    def get_full_pipeline(self, request, pk=None):

        try:

            pipeline = Pipeline.objects.prefetch_related('edges', 'nodes', 'owner').get(id=pk)
            serializer = PipelineDigraphSerializer(pipeline, many=False)
            return Response(serializer.data)

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


    @action(methods=['get'], detail=True)
    def ExportToZip(self, request, pk=None):
        try:
            pipeline = Pipeline.objects.get(pk=pk)
            filename = f"{pipeline.name}.zip"
            export_bytes = exportPipelineToZip(pk)

            print(f"Export bytes: {type(export_bytes)}")

            response = FileResponse(
                export_bytes,
                as_attachment=True,
                filename=filename
            )
            response['Content-Disposition'] = 'attachment; filename={0}'.format(filename)
            response['filename'] = filename

            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


    # Export script as YAML
    @action(methods=['get'], detail=True)
    def ExportToYAML(self, request, pk=None):
        try:
            pipeline = Pipeline.objects.get(pk=pk)
            filename = f"{pipeline.name}.yaml"
            myYaml = io.StringIO()
            yaml = YAML()
            yaml.preserve_quotes = False
            yaml.dump(exportPipelineToYAMLObj(pk), myYaml)

            response = HttpResponse(myYaml.getvalue(), content_type='text/plain',
                                    status=status.HTTP_200_OK)
            response['Content-Disposition'] = 'attachment; filename={0}'.format(filename)
            response['filename'] = filename
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    # Export script as YAML
    @action(methods=['get'], detail=True)
    def ExportToArchive(self, request, pk=None):
        try:
            pipeline = Pipeline.objects.get(pk=pk)
            filename = f"{pipeline.name}.yaml"
            myYaml = io.StringIO()
            yaml = YAML()
            yaml.preserve_quotes = False
            yaml.dump(exportPipelineToYAMLObj(pk), myYaml)

            response = HttpResponse(myYaml.getvalue(), content_type='text/plain',
                                    status=status.HTTP_200_OK)
            response['Content-Disposition'] = 'attachment; filename={0}'.format(filename)
            response['filename'] = filename
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['get'], detail=True)
    def scripts(self, request, pk=None):
        try:
            pipeline = Pipeline.objects.get(pk=pk)
            scripts = PythonScript.objects.filter(pipelinenode__parent_pipeline=pipeline)
            return Response(PythonScriptSummarySerializer(scripts, many=True).data)

        except Exception as e:
            return JsonResponse({"error": "ERROR: {0}".format(e)})


# This mixin lets DRF inbound serialized determine if a list or single object is being passed in... IF, it's a list,
# will instantiate any serializer with the many=True option, allowing for bulk updates and creates.
# https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
# the actual answer in that SO doesn't work right as it can't handle both lists and objects.
class PipelineStepViewSet(ListInputModelMixin, viewsets.ModelViewSet):
    queryset = PipelineNode.objects.all().order_by('-name')
    filter_fields = ['id', 'name', 'parent_pipeline']

    pagination_class = None
    serializer_class = Full_PipelineStepSerializer
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

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

    # Export Node as YAML
    @action(methods=['get'], detail=True)
    def ExportToYAML(self, request, pk=None):
        try:
            filename = f"Node-{pk}.yaml"
            myYaml = io.StringIO()
            yaml = YAML()
            yaml.preserve_quotes = False
            yaml.dump(exportPipelineNodeToYAMLObj(pk), myYaml)
            response = HttpResponse(myYaml.getvalue(), content_type='text/plain', status=status.HTTP_200_OK)
            response['Content-Disposition'] = 'attachment; filename={0}'.format(filename)
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

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
    filter_fields = ['id', 'start_node__id', 'end_node__id', 'parent_pipeline__id']

    pagination_class = None
    serializer_class = EdgeSerializer
    permission_classes = [IsAuthenticated & WriteOnlyIfNotAdminOrEng]

    # Need to inject request user into the serializer
    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    # Export script as YAML
    @action(methods=['get'], detail=True)
    def ExportToYAML(self, request, pk=None):
        try:
            filename = f"Edge-{pk}.yaml"
            myYaml = io.StringIO()
            yaml = YAML()
            yaml.preserve_quotes = False
            yaml.dump(exportPipelineEdgeToYAMLObj(pk), myYaml)
            response = HttpResponse(myYaml.getvalue(), content_type='text/plain', status=status.HTTP_200_OK)
            response['Content-Disposition'] = 'attachment; filename={0}'.format(filename)
            return response

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


class DashboardAggregatesViewSet(APIView):
    allowed_methods = ['get']
    permission_classes = [AdminOrLegalEngAccessOnly]

    def get(self, request, format=None):

        try:

            user_count = User.objects.count()
            doc_count = Document.objects.count()
            parsed_doc_count = Document.objects.filter(extracted=True).count()
            queued_job_count = Job.objects.filter(queued=True).count()
            running_job_count = Job.objects.filter(error=False, started=True, finished=False).count()
            error_job_count = Job.objects.filter(error=True).count()
            script_count = PythonScript.objects.count()
            pipeline_count = Pipeline.objects.count()

            aggregates = {
                "user_count": user_count,
                "doc_count": doc_count,
                "parsed_doc_count": parsed_doc_count,
                "queued_job_count": queued_job_count,
                "running_job_count": running_job_count,
                "error_job_count": error_job_count,
                "script_count": script_count,
                "pipeline_count": pipeline_count
            }

            return JsonResponse(aggregates, status=status.HTTP_200_OK)

        except Exception as e:
            print("Something went wrong trying to prepare aggregates.")
            print(e)
            return Response(e,
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)
