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

from .models import Document, Job, Result, PythonScript, PipelineNode, \
    Pipeline, TaskLogEntry, JobLogEntry, Edge, ScriptDataFile
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
    job_input_json = serializers.CharField(allow_blank=True)
    callback = serializers.CharField(allow_blank=True)

    def create(self, validated_data):

        #Create the job
        job = Job.objects.create(
            name=validated_data['name'],
            owner=validated_data['owner'],
            pipeline=validated_data['pipeline'],
            job_input_json=validated_data['job_input_json'],
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
### PYTHON SCRIPT DATA FILE SERIALIZER
########################################################################################################################

class ScriptDataFileSerializer(serializers.ModelSerializer):

    class Meta:
        model = ScriptDataFile

        fields = ["uuid", "data_file", "manifest", "created", "modified"]
        read_only_fields = ["uuid", "created", "modified", "manifest"]

########################################################################################################################
### PYTHON SCRIPT SERIALIZERS
########################################################################################################################

# This is the most data intensive script serializer. Actually include the script and setup install files
# unlike the SummarySerializer
class PythonScriptSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    data_file = serializers.PrimaryKeyRelatedField(many=False, queryset=ScriptDataFile.objects.all(),
                                                   required=False, allow_null=True, default=None)
    installing = serializers.SerializerMethodField()

    class Meta:
        model = PythonScript

        fields = [
            'id',
            'data_file',
            'owner',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'json_schema',
            'mode',
            'script',
            'description',
            'required_packages',
            'setup_script',
            'env_variables',
            'installer_log',
            'setup_log',
            'locked',
            'installing',
            'install_error',
            'install_error_code'
        ]

        read_only_fields = ['id', 'setup_log', 'owner', 'locked', 'installing',
                            'install_error', 'install_error_code']

    def installing(self, obj):
        return self.installing()


class PythonScriptNestedDataSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    data_file = ScriptDataFileSerializer()
    installing = serializers.SerializerMethodField()

    class Meta:
        model = PythonScript

        fields = [
            'id',
            'data_file',
            'owner',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'json_schema',
            'mode',
            'script',
            'description',
            'required_packages',
            'setup_script',
            'env_variables',
            'installer_log',
            'setup_log',
            'locked',
            'installing',
            'install_error',
            'install_error_code'
        ]

        read_only_fields = ['id', 'setup_log', 'owner', 'locked', 'installing',
                            'install_error', 'install_error_code']

    def installing(self, obj):
        return self.installing()


class PythonScriptSummarySerializer_READ_ONLY(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    data_file = serializers.PrimaryKeyRelatedField(many=False, queryset=ScriptDataFile.objects.all(),
                                                   required=False, allow_null=True, default=None)
    installing = serializers.SerializerMethodField()

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
            'locked',
            'installing',
            'owner',
            'data_file'
        ]
        read_only_fields = [
            'id',
            'name',
            'human_name',
            'type',
            'supported_file_types',
            'description',
            'mode',
            'locked',
            'installing',
            'owner'
        ]

    def locked(self, obj):
        return self.installing()

class PythonScriptSummarySerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    data_file = ScriptDataFileSerializer()
    installing = serializers.SerializerMethodField()

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
            'locked',
            'installing',
            'owner',
            'data_file'
        ]
        read_only_fields = ['id', 'owner', 'locked', 'installing']

    def installing(self, obj):
        return self.installing()

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
    root_node = serializers.PrimaryKeyRelatedField(many=False, queryset=PipelineNode.objects.all(), required=False)

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'json_schema', 'description', 'total_steps', 'owner', 'production', 'locked',
                  'supported_files', 'root_node', 'scale','x_offset', 'y_offset', 'input_json_schema',
                  'install_error', 'install_error_code']
        read_only_fields = ['id', 'total_steps', 'owner', 'supported_files', 'root_node', 'locked',
                  'install_error', 'install_error_code']

# includes nested edge and node objects. These are NOT paginated and are always expected you'd load them for a given pipeline.
# Most likely number will be <100 and probably well under 20 in vast majority of cases. This should not be a very taxing request.
class PipelineDigraphSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.id')

    class Meta:
        model = Pipeline
        depth=1
        fields = ['id', 'name', 'json_schema', 'description', 'total_steps', 'owner', 'production', 'locked',
                  'supported_files', 'root_node', 'scale','x_offset', 'y_offset', 'edges', 'nodes',
                  'install_error', 'install_error_code']
        read_only_fields = ['id', 'total_steps', 'json_schema', 'owner', 'supported_files', 'root_node', 'locked',
                  'install_error', 'install_error_code']

class PipelineSerializer_READONLY(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    root_node = serializers.PrimaryKeyRelatedField(many=False, queryset=PipelineNode.objects.all(), required=False)

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'json_schema', 'description', 'total_steps', 'owner', 'production', 'locked',
                  'supported_files', 'root_node', 'scale','x_offset', 'y_offset']
        read_only_fields = ['id', 'name', 'json_schema', 'description', 'total_steps', 'owner', 'locked'
                            'production', 'supported_files', 'root_node', 'scale','x_offset', 'y_offset']

class JobCreateSerializer(serializers.ModelSerializer):
    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset=Pipeline.objects.all(), required=False)
    num_docs = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job

        fields = ['id', 'name', 'created', 'pipeline', 'queued', 'started',
                  'error', 'finished', 'status', 'start_time', 'stop_time', 'file',
                  'completed_tasks', 'task_count', 'type', 'owner', 'num_docs', 'notification_email', 'job_input_json']

        read_only_fields = ['id', 'created', 'started', 'error', 'finished',
                            'status', 'start_time', 'stop_time', 'file', 'completed_tasks', 'task_count', 'type',
                            'owner', 'num_docs']

class JobSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    pipeline = PipelineSerializer()
    num_docs = serializers.IntegerField(read_only=True)

    class Meta:
        model = Job

        fields = ['id', 'name', 'created', 'pipeline', 'queued', 'started',
                  'error', 'finished', 'status', 'start_time', 'stop_time', 'file',
                  'completed_tasks', 'task_count', 'type', 'owner', 'num_docs', 'notification_email', 'job_input_json']

        read_only_fields = ['id', 'created', 'started', 'error', 'finished',
                            'status', 'start_time', 'stop_time', 'file','completed_tasks','task_count', 'type',
                            'owner', 'num_docs']

class EdgeSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    start_node = serializers.PrimaryKeyRelatedField(many=False, queryset= PipelineNode.objects.all())
    end_node = serializers.PrimaryKeyRelatedField(many=False, queryset= PipelineNode.objects.all())
    parent_pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset= Pipeline.objects.all())

    class Meta:
        model = Edge
        read_only_fields = ['id', 'owner']
        fields = ['id', 'owner', 'start_node', 'end_node', 'label', 'transform_script', 'parent_pipeline']


class PipelineStepSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    script = serializers.PrimaryKeyRelatedField(many=False, queryset= PythonScript.objects.all())
    parent_pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset= Pipeline.objects.all())

    class Meta:
        model = PipelineNode
        read_only_fields =['id', 'owner']
        fields = ['id', 'name', 'type', 'parent_pipeline', 'script', 'step_settings',
                  'input_transform', 'owner', 'x_coord', 'y_coord']

class PipelineStepSerializer_READONLY(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    script = serializers.ReadOnlyField(source='script.id')
    parent_pipeline = serializers.ReadOnlyField(source='parent_pipeline.id')

    class Meta:
        model = PipelineNode
        read_only_fields = ['id', 'name', 'type' 'parent_pipeline', 'script', 'step_settings',
                  'input_transform', 'owner',  'x_coord', 'y_coord']
        fields = ['id', 'name', 'type', 'parent_pipeline', 'script', 'step_settings',
                  'input_transform', 'owner', 'x_coord', 'y_coord']

class Full_PipelineStepSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    script = serializers.PrimaryKeyRelatedField(many=False, queryset= PythonScript.objects.all())
    parent_pipeline = serializers.PrimaryKeyRelatedField(many=False, queryset= Pipeline.objects.all())

    class Meta:
        model = PipelineNode
        read_only_fields = ['id', 'owner']
        fields = ['id', 'type', 'name', 'parent_pipeline', 'script', 'step_settings',
                  'input_transform', 'owner', 'x_coord', 'y_coord']

class PipelineSummarySerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    owner_email = serializers.ReadOnlyField(source='owner.email')

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'description', 'total_steps', 'owner', 'owner_email', 'production', 'supported_files',
                  'input_json_schema']
        read_only_fields = ['id', 'total_steps', 'owner', 'owner_email']

class Full_PipelineSerializer(serializers.ModelSerializer):

    owner = serializers.ReadOnlyField(source='owner.username')
    pipelinenodes = Full_PipelineStepSerializer(many=True, read_only=True)
    root_node = Full_PipelineStepSerializer(many=False, read_only=True, required=False)

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'description', 'total_steps', 'owner', 'production', 'locked',
                  'supported_files', 'pipelinenodes', 'root_node', 'scale', 'x_offset', 'y_offset',
                  'install_error', 'install_error_code', 'json_schema']
        read_only_fields = ['id', 'total_steps', 'owner', 'root_node', 'locked',
                  'install_error', 'install_error_code']

class ResultSummarySerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())
    pipeline_node = serializers.PrimaryKeyRelatedField(many=False, queryset= PipelineNode.objects.all())
    doc = serializers.PrimaryKeyRelatedField(many=False, queryset=Document.objects.all())
    script_id = serializers.ReadOnlyField()

    class Meta:
        model = Result

        fields = ['id', 'name', 'job', 'doc', 'pipeline_node',
                  'start_time', 'stop_time', 'file', 'type', 'owner',
                  'started', 'error', 'finished', 'script_id']
        read_only_fields = ['id', 'name', 'job', 'doc', 'pipeline_node',
                  'start_time', 'stop_time', 'file', 'type', 'owner',
                  'started', 'error', 'finished', 'script_id']

class ResultSerializer(serializers.ModelSerializer):

    owner = serializers.HiddenField(
        default=serializers.CurrentUserDefault()
    )
    job = serializers.PrimaryKeyRelatedField(many=False, queryset=Job.objects.all())
    doc = serializers.PrimaryKeyRelatedField(many=False, queryset=Document.objects.all())
    pipeline_node = serializers.PrimaryKeyRelatedField(many=False, queryset=PipelineNode.objects.all())
    script_id = serializers.ReadOnlyField()

    class Meta:
        model = Result

        fields = ['id', 'name', 'job', 'doc', 'pipeline_node', 'start_time', 'stop_time', 'file', 'has_file', 'type',
                  'owner',  'output_data', 'transformed_input_data', 'raw_input_data',
                  'started', 'error', 'finished', 'script_id', 'node_inputs', 'start_state', 'end_state',
                  'node_output_data']

        read_only_fields = ['id', 'name', 'job', 'doc', 'pipeline_node', 'start_time', 'stop_time', 'has_file', 'file',
                            'type', 'owner', 'output_data', 'transformed_input_data', 'raw_input_data',
                            'started', 'error', 'finished', 'script_id', 'node_inputs', 'start_state',
                            'end_state', 'node_output_data']

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
