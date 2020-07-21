from rest_framework_bulk import BulkSerializerMixin, BulkListSerializer

from .models import Document, Job, Result, PythonScript, PipelineStep, \
    Pipeline, TaskLogEntry, JobLogEntry, ResultInputData, ResultData
from rest_framework import serializers

# This is only used for DRF to request fields necessary to create Docs, parent jobs and start job all in one shot
# It doesn't sit on a real model.
class ProjectSerializer(serializers.Serializer):

    name = serializers.CharField(max_length=512)
    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    file = serializers.FileField(allow_empty_file=False)
    pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset=Pipeline.objects.all())
    job_inputs = serializers.CharField(allow_blank=True)
    callback = serializers.CharField(allow_blank=True)

    def create(self, validated_data):

        #Create the job
        job = Job.objects.create(
            name=validated_data['name'],
            owner=validated_data['owner'],
            pipeline=validated_data['pipeline'],
            job_inputs=validated_data['job_inputs'],
            callback=validated_data['callback']
        )

        #Create the doc
        doc = Document.objects.create(
            file=validated_data['file'],
            name=f"Project {validated_data['name']} - File 0",
            job=job,
            owner=validated_data['owner']
        )

        #Now start the job
        job.queued = True
        job.save()

        return job

########################################################################################################################
### PYTHON SCRIPT SERIALIZERS
########################################################################################################################

# This is the most data intensive script serializer. Actually include the script and setup install files
# unlike the SummarySerializer
class PythonScriptSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = PythonScript

        fields = [
            'id',
            'owner',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'required_inputs',
            'mode',
            'script',
            'description',
            'required_packages',
            'setup_script',
            'env_variables',
            'installer_log',
            'setup_log',
        ]
        read_only_fields = ['id', 'setup_log', 'owner']

class PythonScriptSummarySerializer_READ_ONLY(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = PythonScript

        fields = [
            'id',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'description',
            'mode',
            'owner'
        ]
        fields = [
            'id',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'description',
            'mode',
            'owner'
        ]

class PythonScriptSummarySerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )

    class Meta:
        model = PythonScript

        fields = [
            'id',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'description',
            'mode',
            'owner'
        ]
        read_only_fields = ['id', 'owner']


class DocumentSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())

    class Meta:
        model = Document

        fields = ['id', 'name', 'shortText', 'file', 'type', 'extracted', 'job', 'owner']
        read_only_fields = ['id', 'type', 'owner', 'shortText']


class PipelineSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'schema', 'description', 'total_steps', 'owner', 'production', 'supported_files']
        read_only_fields = ['id', 'total_steps', 'schema', 'owner', 'supported_files']


class PipelineSerializer_READONLY(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'schema', 'description', 'total_steps', 'owner', 'production', 'supported_files']
        read_only_fields = ['id', 'name', 'schema', 'description', 'total_steps', 'owner', 'production', 'supported_files']


class JobSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset=Pipeline.objects.all())
    num_docs = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job

        fields = ['id', 'name', 'creation_time', 'pipeline', 'queued', 'started',
                  'error', 'finished', 'status', 'job_inputs', 'file',
                  'completed_tasks','task_count', 'type', 'owner', 'num_docs']

        read_only_fields = ['id', 'creation_time', 'started', 'error', 'finished',
                            'status', 'file','completed_tasks','task_count', 'type',
                            'owner', 'num_docs']


class PipelineStepSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    script = serializers.PrimaryKeyRelatedField(many=False, queryset= PythonScript.objects.all())
    parent_pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset= Pipeline.objects.all())

    class Meta:
        model = PipelineStep
        read_only_fields =['id', 'owner']
        fields = ['id','name', 'parent_pipeline', 'script', 'step_settings',
                  'step_number', 'input_transform', 'owner']

class PipelineStepSerializer_READONLY(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    script = serializers.ReadOnlyField(source='script.id')
    parent_pipeline = serializers.ReadOnlyField(source='parent_pipeline.id')

    class Meta:
        model = PipelineStep
        read_only_fields = ['id', 'name', 'parent_pipeline', 'script', 'step_settings',
                  'step_number', 'input_transform', 'owner']
        fields = ['id', 'name', 'parent_pipeline', 'script', 'step_settings',
                  'step_number', 'input_transform', 'owner']


class Full_PipelineStepSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    script = PythonScriptSummarySerializer(many=False, read_only=True)
    parent_pipeline = serializers.ReadOnlyField(source='parent_pipeline.id')

    class Meta:
        model = PipelineStep
        read_only_fields = ['id', 'owner']
        fields = ['id', 'name', 'parent_pipeline', 'script', 'step_settings',
                  'step_number', 'input_transform', 'owner']


class Full_PipelineSerializer(serializers.ModelSerializer):
    owner = serializers.ReadOnlyField(source='owner.username')
    pipelinesteps = Full_PipelineStepSerializer(many=True, read_only=True)

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'schema', 'description', 'total_steps', 'owner', 'production',
                  'supported_files', 'pipelinesteps']
        read_only_fields = ['id', 'schema', 'total_steps', 'owner']


class ResultSummarySerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())
    job_step = serializers.PrimaryKeyRelatedField(many=False, queryset= PipelineStep.objects.all())
    doc = serializers.PrimaryKeyRelatedField(many=False, queryset=Document.objects.all())
    input_data = serializers.PrimaryKeyRelatedField(many=False, queryset=ResultInputData.objects.all())
    output_data = serializers.PrimaryKeyRelatedField(many=False, queryset=ResultData.objects.all())

    class Meta:
        model = Result

        fields = ['id', 'name', 'job', 'doc', 'job_step',
                  'start_time', 'stop_time', 'file', 'type', 'owner', 'output_data', 'input_data']
        read_only_fields = ['id', 'name', 'job', 'doc', 'job_step',
                  'start_time', 'stop_time', 'file', 'type', 'owner', 'output_data', 'input_data']

class ResultSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())
    doc = serializers.PrimaryKeyRelatedField(many=False, queryset=Document.objects.all())
    job_step = serializers.PrimaryKeyRelatedField(many=False, queryset=PipelineStep.objects.all())

    class Meta:
        model = Result

        fields = ['id', 'name', 'job', 'doc', 'job_step', 'start_time', 'stop_time', 'file', 'has_file', 'type',
                  'owner', 'output_data_value', 'raw_input_data_value', 'transformed_input_data_value']

        read_only_fields = ['id', 'name', 'job', 'doc', 'job_step', 'start_time', 'stop_time', 'has_file', 'file',
                            'type', 'owner', 'output_data_value', 'raw_input_data_value',
                            'transformed_input_data_value']


class LogSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    result = serializers.PrimaryKeyRelatedField(many=False, queryset=Result.objects.all())

    class Meta:
        model = TaskLogEntry

        fields = ["id","logger_name","level","msg","create_datetime","result", 'owner']
        read_only_fields=["id","logger_name","level","msg","create_datetime","result", 'owner']

class JobLogSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())

    class Meta:
        model = JobLogEntry

        fields = ["id","logger_name","level","msg","create_datetime"]
        read_only_fields=["id","logger_name","level","msg","create_datetime"]
