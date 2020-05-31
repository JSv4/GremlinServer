import logging
import mimetypes
import os
import json
from datetime import datetime

from django.http import FileResponse, JsonResponse
from rest_framework import status
from rest_framework import viewsets, renderers
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_api_key.permissions import HasAPIKey

from Jobs.tasks.task_helpers import transformStepInputs
from .models import Document, Job, Result, PythonScript, PipelineStep, Pipeline, TaskLogEntry, JobLogEntry, \
    ResultData, ResultInputData
from .paginations import MediumResultsSetPagination, LargeResultsSetPagination, SmallResultsSetPagination
from .serializers import DocumentSerializer, JobSerializer, ResultSummarySerializer, PythonScriptSerializer, \
    PipelineSerializer, PipelineStepSerializer, PythonScriptSummarySerializer, LogSerializer, ResultSerializer
from .tasks.tasks import runJob

mimetypes.init()
mimetypes.knownfiles

#constants for logs to convert from # to text
# Enumerations for the task DB logger
LOG_LEVELS = {
    logging.NOTSET: "Not Set",
    logging.INFO: 'Info',
    logging.WARNING: 'Warning',
    logging.DEBUG: 'Debug',
    logging.ERROR: 'Error',
    logging.FATAL: 'Fatal',
}

# From here: https://stackoverflow.com/questions/38697529/how-to-return-generated-file-download-with-django-rest-framework
class PassthroughRenderer(renderers.BaseRenderer):
    """
        Return data as-is. View should supply a Response.
    """
    media_type = ''
    format = ''
    permission_classes = [HasAPIKey | IsAuthenticated]

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
    API endpoint that allows documents to be viewed or created.
    """
    queryset = Document.objects.all().prefetch_related('job').order_by('-name')
    filter_fields = ['id', 'name', 'extracted', 'job']

    pagination_class = MediumResultsSetPagination
    serializer_class = DocumentSerializer
    permission_classes = [HasAPIKey | IsAuthenticated]

    # One way to accept multiple objects via serializer:
    # See https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, many=isinstance(request.data, list))
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    #Super useful docs on routing (unsurprisingly): https://www.django-rest-framework.org/api-guide/routers/
    #Also, seems like there's a cleaner way to do this? Working for now but I don't like it doesn't integrate with Django filters.
    @action(methods=['get'], detail=True, renderer_classes=(PassthroughRenderer,))
    def download(self, request, pk=None):

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

    queryset = TaskLogEntry.objects.select_related('owner','result').all().order_by('create_datetime')
    filter_fields = ['result']

    pagination_class = MediumResultsSetPagination
    serializer_class = LogSerializer
    permission_classes = [HasAPIKey | IsAuthenticated]


class JobLogViewSet(viewsets.ModelViewSet):

    queryset = JobLogEntry.objects.all().order_by('create_datetime')
    filter_fields = ['job']

    pagination_class = MediumResultsSetPagination
    serializer_class = LogSerializer
    permission_classes = [HasAPIKey | IsAuthenticated]


class JobViewSet(viewsets.ModelViewSet):

    queryset = Job.objects.select_related('owner', 'pipeline').all().order_by('-name')
    filter_fields = ['name','id', 'status', 'started', 'queued', 'finished', 'type']

    pagination_class = None
    serializer_class = JobSerializer
    permission_classes = [HasAPIKey | IsAuthenticated]

    # This action will run a job up through a certain step of its pipeline
    # e.g. if we called .../Job/1/RunToStep/2 that would run the job 1 pipeline to step index 2 (#3)
    # if the provided step_number is out of range, the whole pipeline will run.
    @action(methods=['get'], detail=True, url_name='RunToStep', url_path='RunToStep/(?P<step_number>[0-9]+)')
    def runToStep(self, request, pk=None, step_number=None):
        try:
            print(pk)
            print(step_number)
            runJob.delay(jobId=pk, endStep= int(step_number))
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
            deleted_ids=[]
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
            return JsonResponse({"data":{'id':pk, 'taskCount':job.task_count()}})
        except Exception as e:
            return JsonResponse({'data':{'id':pk, 'error': f"{e}"}})

    @action(methods=['get'], detail=True)
    def get_job_results_with_data(self, request, pk = None):
        try:
            results = Result.objects.filter(job=pk)
            serializer = ResultSerializer(results, many=True)
            return Response(serializer.data)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)


class FileResultsViewSet(viewsets.ModelViewSet):
    queryset = Result.objects.select_related('owner','job','job_step','doc','input_data','output_data').exclude(file='')
    filter_fields = ['id', 'job__id', 'start_time', 'stop_time']
    pagination_class = SmallResultsSetPagination
    serializer_class = ResultSummarySerializer
    permission_classes = [HasAPIKey | IsAuthenticated]


class ResultsViewSet(viewsets.ModelViewSet):

    queryset = Result.objects.select_related('owner','job','job_step','doc','input_data','output_data').all().order_by('-job__id')
    filter_fields = ['id', 'job__id', 'start_time', 'stop_time']

    pagination_class = LargeResultsSetPagination
    serializer_class = ResultSummarySerializer
    permission_classes = [HasAPIKey | IsAuthenticated]

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
                if log.trace: stackTrace = stackTrace + "\n({0}) {1} --- \n\tMessage: {2}\n\nn\tTrace: {3}".format(log.level, log.create_datetime, log.msg, log.trace)
            return JsonResponse({"log":logTxt,"stackTrace":stackTrace,"error":error,"warnings":warn})

        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

class PythonScriptViewSet(viewsets.ModelViewSet):

    queryset = PythonScript.objects.select_related('owner').all().order_by('-name')
    filter_fields = ['id', 'mode', 'type', 'human_name']

    pagination_class = None
    serializer_class = PythonScriptSummarySerializer
    permission_classes = [HasAPIKey | IsAuthenticated]

    #I want to use different serializer for create vs other actions.
    #Based on the guidance here:https://stackoverflow.com/questions/22616973/django-rest-framework-use-different-serializers-in-the-same-modelviewset
    def get_serializer_class(self):
        if self.action == 'create': #for create only, provided option to pass in script.
            return PythonScriptSerializer
        return PythonScriptSummarySerializer  # For list, update, delete, and all other actions

    #Rather than have every script list request cost enormous amounts of data, have client request script details on a
    #script-by-script basis
    @action(methods=['get'], detail=True)
    def GetDetails(self, request, pk=None):
        try:
            script = PythonScript.objects.get(id=pk)
            serializer = PythonScriptSerializer(script)
            return Response(serializer.data)
        except Exception as e:
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)

    #Just as I'm trying to cut down on load times and data usage for scripts with loads with the "GetDetails"
    #action above, I similarly want to require updates to the meaty parts of a script (the script code),
    #etc, to go through a separate action.
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

class PipelineViewSet(viewsets.ModelViewSet):

    queryset = Pipeline.objects.all().order_by('-name')
    filter_fields = ['id','name']

    pagination_class = None
    serializer_class = PipelineSerializer
    permission_classes = [HasAPIKey | IsAuthenticated]

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
            name="TEST JOB",
            type="TEST",
            creation_time=datetime.now(),
            pipeline=pipeline
        )

        serializer = JobSerializer(test_job, many=False)
        return Response(serializer.data)


#This mixin lets DRF inbound serialized determine if a list or single object is being passed in... IF, it's a list,
#will instantiate any serializer with the many=True option, allowing for bulk updates and creates.
#https://stackoverflow.com/questions/14666199/how-do-i-create-multiple-model-instances-with-django-rest-framework
#the actual answer in that SO doesn't work right as it can't handle both lists and objects.
class PipelineStepViewSet(ListInputModelMixin, viewsets.ModelViewSet):

    queryset = PipelineStep.objects.all().order_by('-name')
    filter_fields = ['id', 'name', 'parent_pipeline']

    pagination_class = None
    serializer_class = PipelineStepSerializer
    permission_classes = [HasAPIKey | IsAuthenticated]

    @action(methods=['get'], detail=True, url_name='JobLogs', url_path='JobLogs/(?P<job_id>[0-9]+)')
    def logs(self, request, pk=None, job_id=None):
        try:
            results = Result.objects.filter(job_step=pk, job=job_id)
            logText = ""
            print(len(results))

            for count, result in enumerate(results):
                logText = logText + "\n--- Result {0} of {1}: {2}\n".format(count+1, len(results), result.name)
                logs = TaskLogEntry.objects.filter(result=result.pk)
                print(len(logs))
                for log in reversed(logs):
                    logText = logText + "\n\t({0}) {1} --- ".format(LOG_LEVELS[log.level], log.create_datetime) + log.msg

            return JsonResponse({"log": logText, "error":""})

        except Exception as e:
            return JsonResponse({"log":"No logs", "error": "ERROR: {0}".format(e)})

    @action(methods=['put'], detail=False)
    def test_transform_script(self, request):
        try:
            input_data = request.data['input_data']
            input_transform = request.data['input_transform']
            return_data = {"error":"No errors."}

            if input_transform:
                return_data['output_data'] = transformStepInputs(input_transform, input_data)
            else:
                return_data['output_data'] = input_data

            return JsonResponse(return_data)

        except Exception as e:
            return JsonResponse({"output_data":{}, "error": "ERROR: {0}".format(e)})

    @action(methods=['put'], detail=True)
    def test_step_transform_script(self, request, pk=None):
        try:
            step = PipelineStep.objects.get(id=pk)
            input_data = request.data['input_data']
            return_data = {"error": "No errors."}

            if step.input_transform:
                return_data['output_data'] = transformStepInputs(step.input_transform, input_data)
            else:
                return_data['output_data'] = input_data

            return JsonResponse(return_data)

        except Exception as e:
            return JsonResponse({"output_data": {}, "error": "ERROR: {0}".format(e)})
