import logging, os, operator
from django.db import models
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

	logger_name = models.CharField(max_length=100)
	level = models.PositiveSmallIntegerField(choices=LOG_LEVELS, default=logging.ERROR, db_index=True)
	msg = models.TextField()
	trace = models.TextField(blank=True, null=True)
	create_datetime = models.DateTimeField(auto_now_add=True, verbose_name='Created at')
	result = models.ForeignKey("Result", blank=False, null=False, on_delete=models.CASCADE)

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
	description = models.TextField("Script Description", blank=True, null=False, default="")

	# Supported document types (this will be a serialized list of supported extensions - e.g. .pdf, .doc, .docx, etc.)
	supported_file_types = models.TextField("Supported File Types", blank=False, default='[".pdf"]')

	# The actual python code to execute
	script = models.TextField("Python Code", blank=True, null=False, default="")

	# the list of python packages to install (use pip requirements.txt format)
	required_packages = models.TextField("Required Python Packages", blank=True, null=False, default="")

	# code to call after install required packages but before this script is ready (e.g. NLTK data files)
	setup_script = models.TextField("Python setup script", blank=True, null=False, default="")

	# Expected JsonSchema goes here. Based on v7 of JsonSchema. For now, this needs to be entered manually.
	required_inputs = models.TextField("Required Inputs", blank=True, default="")

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
	started_steps = models.ManyToManyField("PipelineStep", blank=True)

	# Data variables
	job_inputs = models.TextField("Input Json", blank=True, default="")

	# Related Files
	file = models.FileField("Output File Zip", upload_to='jobs_data/results/', blank=True, null=True)

	def __str__(self):
		return self.name

	def pipeline_steps(self):
		try:
			return PipelineStep.objects.filter(parent_pipeline=self.pipeline.id).all()
		except:
			return []

	def task_count(self):
		if self.pipeline:
			return self.pipeline.total_steps
		else:
			return 0


class Pipeline(models.Model):

	# Line Meta Data
	name = models.CharField(max_length=512, default="Line Name", blank=False)
	description = models.TextField(default="",blank=True)

	owner = models.ForeignKey(
		get_user_model(),
		on_delete=models.CASCADE,
		default=1
	)

	total_steps = models.IntegerField("Step Count", blank=False, default=0)
	schema = models.TextField("Job Settings", blank=True, default="")

	def __str__(self):
		return self.name

class PipelineStep(models.Model):

	### CONSTRAINTS ################################################################################

	# This lets you create a unique constraint as a combination of fields, such as, for example,
	# having a unique step_number for any given parent_pipeline
	constraints = [
		models.UniqueConstraint(fields=['parent_pipeline', 'step_number'], name='unique step number')
	]

	### FIELDS #####################################################################################
	#What is the control job and what is the python scripy
	script = models.ForeignKey(PythonScript, on_delete=models.SET_NULL, null=True)

	# Job Meta Data
	name = models.CharField(max_length=512, default="Step Name", blank=False)

	owner = models.ForeignKey(
		get_user_model(),
		on_delete=models.CASCADE,
		default=1
	)

	# Mapping script... will be use to transform data coming into the script. Helpful in building pipelines where
	# you probably want to transform input data.
	input_transform = models.TextField("Input Transformation", blank=True, null=False, default="")

	#Persisted settings - these will get overriden by any job_settings for this step that have conflicting
	#keys. The overwrite happens in the tasks.py module.
	step_settings = models.TextField("Step Settings", blank=True, default="")

	# Process variables
	parent_pipeline = models.ForeignKey("Pipeline", null=True, on_delete=models.SET_NULL)
	step_number = models.IntegerField(blank=False, default=-1)

	### Methods #####################################################################################

	def __str__(self):
		return self.name

class DocumentText(models.Model):

	owner = models.ForeignKey(
		get_user_model(),
		on_delete=models.CASCADE,
		default=1
	)

	rawText = models.TextField("Extracted Text", blank=False, null=True, default="")

class Document(models.Model):

	owner = models.ForeignKey(
		get_user_model(),
		on_delete=models.CASCADE,
		default=1
	)

	name = models.CharField("Document Name", max_length=512, default="Contract", blank=False)
	pageCount = models.IntegerField("Number of Pages", blank=False, default=1)
	textObj = models.ForeignKey(DocumentText, null=True, on_delete=models.CASCADE)
	type = models.CharField("File Extension", max_length=5, default="", blank=False)
	file = models.FileField("Original File", upload_to='uploads/contracts/')
	extracted = models.BooleanField("Extracted Successfully", default=False)
	results = models.ManyToManyField("Result", blank=True)
	jobs = models.ManyToManyField(Job, blank=True)

	def rawText(self):
		if self.textObj:
			return self.text_obj.rawText
		return None

	#don't want to return shortText by default as it can go on for a looooong, loooong time.
	def shortText(self):
		return self.rawText()[0:199] if (self.rawText() and len(self.rawText())>200) else self.rawText()

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
	job_step = models.ForeignKey(PipelineStep, on_delete=models.CASCADE, null=True)
	doc = models.ForeignKey(Document, on_delete=models.SET_NULL, null=True)

	# Timing variables
	start_time = models.DateTimeField("Step Start Date and Time", blank=True, null=True)
	stop_time = models.DateTimeField("Step Stop Date and Time", blank=True, null=True)

	# Inputs
	input_settings = models.TextField("Input Settings", blank=True, null=False, default="") # what input_setting were passed in
	input_data = models.ForeignKey('ResultInputData', null=True, on_delete=models.SET_NULL)

	# Outputs
	output_data = models.ForeignKey('ResultData', null=True, on_delete=models.SET_NULL)
	file = models.FileField("Results File", upload_to='results/results/', blank=True, null=True)

	def has_file(self):
		if self.file:
			return True
		else:
			return False

	def output_data_value(self):

		jsonObj = None

		if self.output_data:
			try:
				jsonObj = json.loads(self.output_data.output_data)
			except:
				pass

		return jsonObj

	def raw_input_data_value(self):

		jsonObj = None

		if self.input_data:
			try:
				jsonObj = json.loads(self.input_data.raw_input_data)
			except:
				pass

		return jsonObj

	def transformed_input_data_value(self):

		jsonObj = None

		if self.input_data:
			try:
				jsonObj = json.loads(self.input_data.transformed_input_data)
			except:
				pass

		return jsonObj

	def __str__(self):
		if self.job_step:
			return "Job {0} Step {0} Result".format(self.job.name, self.job_step.name)
		else:
			return "Job {0} Result".format(self.job.name)

class ResultData(models.Model):

	owner = models.ForeignKey(
		get_user_model(),
		on_delete=models.CASCADE,
		default=1
	)

	output_data = models.TextField("Output JSON Data", blank=False, null=False, default="")

class ResultInputData(models.Model):

	owner = models.ForeignKey(
		get_user_model(),
		on_delete=models.CASCADE,
		default=1
	)

	transformed_input_data: TextField = models.TextField("Transformed Input Json Data", blank=True, null=False, default="")
	raw_input_data: TextField = models.TextField("Raw Input Json Data", blank=True, null=False, default="")
