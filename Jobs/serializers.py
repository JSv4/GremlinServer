from rest_framework_bulk import BulkSerializerMixin, BulkListSerializer

from .models import Document, Job, Result, PythonScript, PipelineStep, \
    Pipeline, TaskLogEntry, JobLogEntry, ResultInputData, ResultData
from rest_framework import serializers

class DocumentSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())

    class Meta:
        model = Document

        fields = ['id', 'name', 'shortText', 'file', 'type', 'extracted', 'job', 'owner']
        read_only_fields = ['id', 'type', 'owner', 'shortText']

class PipelineSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'schema', 'description', 'total_steps', 'owner']
        read_only_fields = ['id', 'total_steps', 'schema', 'owner']


class JobSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset=Pipeline.objects.all())

    class Meta:
        model = Job

        fields = ['id', 'name', 'creation_time', 'pipeline', 'queued', 'started',
                  'error', 'finished', 'status', 'job_inputs', 'file',
                  'completed_tasks','task_count', 'type', 'owner']

        read_only_fields = ['id', 'creation_time', 'started', 'error', 'finished',
                            'status', 'file','completed_tasks','task_count', 'type', 'owner']

class PipelineStepListSerializer(serializers.ListSerializer):

    def update(self, instance, validated_data):
        # Maps for id->instance and id->data item.
        pipelinestep_mapping = {pipelinestep.id: pipelinestep for pipelinestep in instance}
        data_mapping = {item['id']: item for item in validated_data}

        # Perform creations and updates.
        ret = []
        for pipelinestep_id, data in data_mapping.items():
            pipelinestep = pipelinestep_mapping.get(pipelinestep_id, None)
            if pipelinestep is None:
                ret.append(self.child.create(data))
            else:
                ret.append(self.child.update(pipelinestep, data))

        return ret

class PipelineStepSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    script = serializers.PrimaryKeyRelatedField(many=False, queryset= PythonScript.objects.all())
    parent_pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset= Pipeline.objects.all())

    class Meta:
        model = PipelineStep
        read_only_fields =['id', 'owner']
        fields = ['id','name', 'parent_pipeline', 'script', 'step_settings',
                  'step_number', 'input_transform', 'owner']

class ResultSummarySerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
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

    owner = serializers.ReadOnlyField(source='owner.username')
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

#Actually include the script and setup install files unlike the ShortScriptSerializer
class PythonScriptSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = PythonScript

        fields = [
            'id',
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
            'owner'
        ]
        read_only_fields = ['id', 'owner', 'setup_log']

#Actually include the script and setup install files unlike the ShortScriptSerializer
class PythonScriptSummarySerializer(serializers.ModelSerializer):

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
        read_only_fields = ['id', 'owner']

class LogSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    result = serializers.PrimaryKeyRelatedField(many=False, queryset=Result.objects.all())

    class Meta:
        model = TaskLogEntry

        fields = ["id","logger_name","level","msg","create_datetime","result", 'owner']
        read_only_fields=["id","logger_name","level","msg","create_datetime","result", 'owner']

class JobLogSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())

    class Meta:
        model = JobLogEntry

        fields = ["id","logger_name","level","msg","create_datetime"]
        read_only_fields=["id","logger_name","level","msg","create_datetime"]
