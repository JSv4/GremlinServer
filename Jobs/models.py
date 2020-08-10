import logging, os, operator
from django.db import models
from django.contrib.postgres.fields import JSONField
from django import utils
from django.contrib.auth import get_user_model
from django.db.models import TextField
from django.utils.translation import ugettext_lazy as _
import json

class TaskLogEntry(models.Model):

    # Enumerations for the task DB logger
    LOG_LEVELS = (
        (logging.NOTSET, _('NotSet')),
        (logging.INFO, _('Info')),
        (logging.WARNING, _('Warning')),
        (logging.DEBUG, _('Debug')),
        (logging.ERROR, _('Error')),
        (logging.FATAL, _('Fatal')),
    )

    # for later... if we want to try to segregate everything by user accounts
    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    result = models.ForeignKey("Result", blank=False, null=False, on_delete=models.CASCADE)

    logger_name = models.CharField(max_length=100)
    level = models.PositiveSmallIntegerField(choices=LOG_LEVELS, default=logging.ERROR, db_index=True)
    msg = models.TextField(blank=True, default="")
    trace = models.TextField(blank=True, default="")
    create_datetime = models.DateTimeField(auto_now_add=True, verbose_name='Created at')

    def __str__(self):
        return self.msg

    class Meta:
        ordering = ('-create_datetime',)
        verbose_name_plural = verbose_name = 'Task Log Entries'

class JobLogEntry(models.Model):

    # Enumerations for the task DB logger
    LOG_LEVELS = (
        (logging.NOTSET, _('NotSet')),
        (logging.INFO, _('Info')),
        (logging.WARNING, _('Warning')),
        (logging.DEBUG, _('Debug')),
        (logging.ERROR, _('Error')),
        (logging.FATAL, _('Fatal')),
    )

    # for later... if we want to try to segregate everything by user accounts
    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    logger_name = models.CharField(max_length=100)
    level = models.PositiveSmallIntegerField(choices=LOG_LEVELS, default=logging.ERROR, db_index=True)
    msg = models.TextField()
    trace = models.TextField(blank=True, null=True)
    create_datetime = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
    job = models.ForeignKey("Job", blank=False, null=False, on_delete=models.CASCADE)

    def __str__(self):
        return self.msg

    class Meta:
        ordering = ('-create_datetime',)
        verbose_name_plural = verbose_name = 'Job Log Entries'

class PythonScript(models.Model):

    # Job Type Choices
    RUN_ON_JOB_ALL_DOCS_PARALLEL = "RUN_ON_JOB_DOCS_PARALLEL"
    RUN_ON_JOB = 'RUN_ON_JOB'
    RUN_ON_PAGE = 'RUN_ON_PAGE'

    SCRIPT_TYPE = [
        (RUN_ON_JOB, _('Run on Job Data (For monolith scripts)')),
        (RUN_ON_JOB_ALL_DOCS_PARALLEL, _('Run on Each Doc in Job (Parallel Execution)')),
        (RUN_ON_PAGE, _('Run on Each Page of Doc (Sharded Execution)')),
    ]

    # Script enumerations for type (ready for deployment vs test)
    TEST = 'TEST'
    DEPLOYED = 'DEPLOYED'
    RUN_MODE = [
        (TEST, _('Test Mode')),
        (DEPLOYED, _('Ready for Deployment')),
    ]

    #for later... if we want to try to segregate everything by user accounts
    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    # will be used to generate a package name
    name = models.CharField("Lookup Name", max_length=256, blank=False, null=False, default="")
    human_name = models.CharField("Human Readable Name", max_length=32, blank=False, null=False, default="")

    # pretty self-explanatory... whill this be a run accross all docs in paralle or serial (some jobs are hard to parallelize)
    type = models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=SCRIPT_TYPE,
        default=RUN_ON_JOB,
    )

    # Description of the python script
    description = models.TextField("Script Description", blank=True, default="")

    # Supported document types (this will be a serialized list of supported extensions - e.g. .pdf, .doc, .docx, etc.)
    supported_file_types = models.TextField("Supported File Types", blank=False, default='[".pdf"]')

    # The actual python code to execute
    script = models.TextField("Python Code", blank=True, default="")

    # the list of python packages to install (use pip requirements.txt format)
    required_packages = models.TextField("Required Python Packages", blank=True, default="")

    # code to call after install required packages but before this script is ready (e.g. NLTK data files)
    setup_script = models.TextField("Python setup script", blank=True, default="")

    # stringified json representation of env varis
    env_variables = models.TextField("Environment Variables", blank=True, default="")

    # Expected JsonSchema goes here. Based on v7 of JsonSchema. For now, this needs to be entered manually.
    schema = models.TextField("Input Schema", blank=True, default="")

    # is this script ready to use (have all imports and setup steps been executed?)
    mode = models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=RUN_MODE,
        default=TEST,
    )

    # place to store the latest results of package installer...
    installer_log = models.TextField("Installation Log", blank=True, default="")

    # place to store the last results of the setup script
    setup_log = models.TextField("Setup Log", blank=True, default="")

    def __str__(self):
        return self.human_name

class Job(models.Model):

    # Script enumerations for type (ready for deployment vs test)
    TEST = 'TEST'
    PRODUCTION = 'PRODUCTION'
    JOB_TYPE = [
        (TEST, _('Test')),
        (PRODUCTION, _('Production')),
    ]

    # pretty self-explanatory... whill this be a run accross all docs in paralle or serial (some jobs are hard to parallelize)
    type = models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=JOB_TYPE,
        default=PRODUCTION,
    )

    # Job Meta Data
    name = models.CharField(max_length=512, default="Job Name", blank=False)

    # Timing variables
    creation_time = models.DateTimeField("Job Creation Date and Time", default=utils.timezone.now)

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    #Which line to use?
    pipeline = models.ForeignKey("Pipeline", on_delete=models.SET_NULL, null=True)

    # Control variables
    queued = models.BooleanField("Job Queued", default=False, blank=False)
    started = models.BooleanField("Job Started", default=False, blank=False)
    error = models.BooleanField("Job in Error Status", default=False, blank=False)
    finished = models.BooleanField("Job Finished", default=False, blank=False)
    status = models.TextField("Job Status", default="Not Started", blank=False)
    completed_tasks = models.IntegerField("Completed Step Tasks", default=0, blank=False)

    # API Integration values
    callback = models.TextField("Callback URL", default="", blank=True,)

    # Data variables
    job_inputs = models.TextField("Input Json", blank=True, default="")

    # Related Files
    file = models.FileField("Output File Zip", upload_to='data/jobs_data/results/', blank=True, null=True)

    def __str__(self):
        return self.name

    def pipeline_steps(self):
        try:
            return PipelineNode.objects.filter(parent_pipeline=self.pipeline.id).all()
        except:
            return []

    def task_count(self):
        if self.pipeline:
            return self.pipeline.total_steps
        else:
            return 0


class Pipeline(models.Model):

    name = models.CharField("Pipeline Name", max_length=512, default="Line Name", blank=False)
    description = models.TextField("Pipeline Description", default="", blank=True)
    production = models.BooleanField("Available in Production", default=False, blank=True)

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    total_steps = models.IntegerField("Step Count", blank=False, default=0)
    schema = models.TextField("Pipeline Schema", blank=True, default="")
    supported_files = models.TextField("Supported File Types", blank=True, default="")

    root_node = models.ForeignKey("PipelineNode", blank=True, null=True, on_delete=models.SET_NULL)

    # Rendering variables for frontend
    scale = models.FloatField("View Scale Factor", blank=False, default=1.0)
    x_offset = models.IntegerField("X Offset", blank=False, default=0)
    y_offset = models.IntegerField("Y Offset", blank=False, default=0)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):

        # If this is a new model, create the root node (the relationship to which can't be changed via the serializers,
        # though the node itself can be modified):
        #
        # How to tell if save is new save or update (apparently it's not well-documented):
        # https://stackoverflow.com/questions/907695/in-a-django-model-custom-save-method-how-should-you-identify-a-new-object
        if self._state.adding:

            # If this is a new pipeline, create the root node.
            # Once we switch to the new node and edge architecture, there will be no need to create or manage
            # "step_number" value...

            super(Pipeline, self).save(*args, **kwargs)

            root = PipelineNode.objects.create(**{
                "type": PipelineNode.ROOT_NODE,
                "script": None,
                "name": "Pre-Processor",
                "owner": self.owner,
                "parent_pipeline": self,
                "step_number": 0
            })

            # Link the new root_node type node to the root_node of the pipeline that's being created
            self.root_node = root

            self.save()

        else:
            super(Pipeline, self).save(*args, **kwargs)

class PipelineNode(models.Model):

    ### CONSTRAINTS ################################################################################

    # This lets you create a unique constraint as a combination of fields, such as, for example,
    # having a unique step_number for any given parent_pipeline
    constraints = [
        models.UniqueConstraint(fields=['parent_pipeline', 'step_number'], name='unique step number')
    ]

    ### FIELDS #####################################################################################
    #What is the control job and what is the python scripy
    script = models.ForeignKey(PythonScript, on_delete=models.SET_NULL, null=True)

    # Node Type Choices
    SCRIPT = "THROUGH_SCRIPT"
    ROOT_NODE = 'ROOT_NODE'
    PACKAGING_NODE = 'PACKAGING_NODE'
    CALLBACK = 'CALLBACK'
    API_REQUEST = 'API_REQUEST'

    NODE_TYPE = [
        (SCRIPT, _('Python Script')),
        (ROOT_NODE, _('Root node - provides data, doc and setting.')),
        (PACKAGING_NODE, _('Packaging node - instructions to package results.')),
        (CALLBACK, _('Callback - send data or docs out to external API')),
        (API_REQUEST, _('API Request - request data or docs from an external API')),
    ]

    type = models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=NODE_TYPE,
        default=SCRIPT,
    )

    name = models.CharField(max_length=512, default="Step Name", blank=False)

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    # Mapping script... will be use to transform data coming into the script. Helpful in building pipelines where
    # you probably want to transform input data.
    input_transform = models.TextField("Input Transformation", blank=True, default="")

    # Persisted settings - these will get overriden by any job_settings for this step that have conflicting
    # keys. The overwrite happens in the tasks.py module.
    step_settings = models.TextField("Step Settings", blank=True, default="")

    # Frontend Render Variables
    x_coord = models.FloatField("X Coordinate", default=0, blank=False)
    y_coord = models.FloatField("Y Coordinate", default=0, blank=False)

    # Process variables - Will deprecate step_number
    parent_pipeline = models.ForeignKey("Pipeline", related_name="pipelinenodes", null=True, on_delete=models.SET_NULL)
    step_number = models.IntegerField(blank=False, default=-1)

    ### Methods #####################################################################################

    def __str__(self):
        return self.name


# Models connection between pipelinenodes (nodes)
class Edge(models.Model):

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    label = models.TextField("Link Label", blank=True, default="")
    start_node = models.ForeignKey(PipelineNode, null=True, related_name='out_edges', on_delete=models.CASCADE)
    end_node = models.ForeignKey(PipelineNode, null=True, related_name='in_edges', on_delete=models.CASCADE)
    transform_script = models.TextField("Data Transform Script", blank=True, default="")
    parent_pipeline = models.ForeignKey(Pipeline, null=True, blank=False, related_name='pipeline_edges', on_delete=models.CASCADE)

class Document(models.Model):

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    name = models.CharField("Document Name", max_length=512, default="Contract", blank=False)
    pageCount = models.IntegerField("Number of Pages", blank=False, default=1)
    rawText = models.TextField("Raw Text", blank=False, default="")
    type = models.CharField("File Extension", max_length=5, default="", blank=False)
    file = models.FileField("Original File", upload_to='data/uploads/docs/')
    extracted = models.BooleanField("Extracted Successfully", default=False)
    job = models.ForeignKey(Job, null=True, on_delete=models.CASCADE)

    #don't want to return shortText by default as it can go on for a looooong, loooong time.
    def shortText(self):
        return self.rawText[0:199] if (self.rawText and len(self.rawText)>200) else self.rawText

    def __str__(self):
        return self.name

    # Override the save method so that the file type is automatically pulled from the filename
    def save(self, *args, **kwargs):
        if self.file:
            filename = self.file.name
            name, file_extension = os.path.splitext(filename)
            self.type = file_extension
        else:
            self.type = ""

        super(Document, self).save(*args, **kwargs)

class Result(models.Model):

    # Script enumerations for type (ready for deployment vs test)
    DOC = 'DOC'
    STEP = 'STEP'
    JOB = 'JOB'
    RESULT_TYPE = [
        (DOC, _('Doc Result')),
        (STEP, _('Step Result')),
        (JOB, _('Job Result')),
    ]

    owner = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        default=1
    )

    #metadata
    name = models.CharField("Result Name", max_length=512, default="Result", blank=False, null=False)
    type = models.CharField(
        max_length=128,
        blank=False,
        null=False,
        choices=RESULT_TYPE,
        default=JOB,
    )

    #Relationships
    job = models.ForeignKey(Job, on_delete=models.CASCADE, null=False)
    pipeline_node = models.ForeignKey(PipelineNode, on_delete=models.CASCADE, null=True)
    doc = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True)

    # Timing variables
    start_time = models.DateTimeField("Step Start Date and Time", blank=True, null=True)
    stop_time = models.DateTimeField("Step Stop Date and Time", blank=True, null=True)

    # Inputs
    input_settings = models.TextField("Input Settings", blank=True, default="{}") # what input_setting were passed in
    transformed_input_data = models.TextField("Transformed Input Json Data", blank=True, default="{}")
    raw_input_data = models.TextField("Raw Input Json Data", blank=True, default="{}")

    # Outputs
    output_data = models.TextField('Result Data', blank=False, default="{}")
    file = models.FileField("Results File", upload_to='data/results/results/', blank=True, null=True)

    def has_file(self):
        if self.file:
            return True
        else:
            return False

    def __str__(self):
        if self.pipeline_node:
            return "Job {0} Step {0} Result".format(self.job.name, self.pipeline_node.name)
        else:
            return "Job {0} Result".format(self.job.name)
