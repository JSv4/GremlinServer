from celery import chain
import json
import operator
from django.db import transaction

from .tasks.tasks import runJob, installPackages, runPythonScriptSetup, \
	createNewPythonPackage, extractTextForDoc, updatePythonPackage, deletePythonPackage
from .models import PipelineStep, Pipeline


def run_job_on_queued(sender, instance, created, **kwargs):

	if instance.queued and not instance.started and not instance.error and not instance.finished:
		runJob.delay(instance.id)


# When a new document is created... start text extraction by default
def process_doc_on_create(sender, instance, created, **kwargs):

	if created:
		extractTextForDoc.delay(instance.id)

# https://stackoverflow.com/questions/53503460/possible-race-condition-between-django-post-save-signal-and-celery-task
# https://stackoverflow.com/questions/45276828/handle-post-save-signal-in-celery
def process_doc_on_create_atomic(sender, instance, created, **kwargs):

    if created:
        transaction.on_commit(lambda: extractTextForDoc.delay(instance.id))


def renumber_pipeline_steps_on_create_or_update(sender, instance: PipelineStep, **kwargs):

	print("renumber_pipeline_steps_on_create_or_update")
	print(f"Instance: {instance.step_number}")
	# If the step is part of a pipeline calculate proper pipeline ordering... otherwise set step_number = 0
	if instance.parent_pipeline:

		print(f"Has parent_pipeline:{instance.parent_pipeline}")
		pipelineSteps = PipelineStep.objects.filter(parent_pipeline=instance.parent_pipeline.id).all()
		stepCount = len(pipelineSteps)

		print(f"Pipeline step count is {stepCount}")

		# If there are no steps... just add at step_number 0
		if stepCount == 0:
			print(f"Target step_number is 0... set number = 0")
			instance.step_number = 0

		# If we try to add at negative step_number of a step_number > stepCount, then add at end.
		elif instance.step_number < 0 or instance.step_number > stepCount:
			print(f"Target step_number is less than 0, add to end of pipeline @ StepCount: {stepCount}")
			instance.step_number = stepCount # Think this should be stepCount - 1. Wait actually don't think so because that's the count without new step.

		# Otherwise, we're introducing a conflicting step_number and need to renumber the pipeline.
		else:

			# If the instance is new... we don't need to worry about renumbering steps between its original position
			# (As it's non-existant) and it's target position. Otherwise, we do need to reduce the indices of the
			# Steps after original position but before target position.

			old_number = -1

			# If the instance.id is NOT None and this is NOT a new object, get the original step_number prior to save.
			if instance.id is not None:  # new object will be created
				try:
					print("filtered pipelineSteps")
					print(filter(lambda step : step.id==instance.id, pipelineSteps))
					old_number = list(filter(lambda step : step.id==instance.id, pipelineSteps))[0].step_number
					print(f"This was an pre-existing step, old step_number is {old_number}")
				except Exception as e:
					print(f"ERROR fetching old pipelineStep step_number: {e}")

			print("You chose to drop this in the middle of the existing pipeline...")

			stepList = []

			#build a list of the steps held in tuples, with step_number, step pairs
			print("Current pipelineSteps:")
			for index, step in enumerate(pipelineSteps):
				print(f"Step #{step.step_number}: {step}")
				if step.id is not instance.id:
					stepList.append((step.step_number, step))

			#sort the list
			stepList.sort(key=operator.itemgetter(0))
			print(f"sorted stepList: {stepList}")

			#insert the new instance where it's supposed to go. This is post sort. Don't resort.
			stepList.insert(instance.step_number, (instance.step_number, instance))

			#now traverse the sorted list, start renumbering using new indices at one of two spots depending
			for index, (step_number, step) in enumerate(stepList):

				print(f"Index @{index}: step_number {step_number} and step={step}")

				# don't renumber the new instance as that's the post_save value of renumbered step.
				if step.id is not instance.id:

					print("This is not the moved step.")

					# If this was a pre-existing step moved from inside the pipeline, renumber once we get to index
					# of its original position (old_number).
					if old_number != -1:
						print("Not moved pipelineStep... renumber")

						print(f"old_number is not -1: (it's {old_number}). This means this was moved "
						      f"from in the pipeline somewhere. Only renumber from where this was moved from.")
						if index >= old_number:
							print(f"index {index} >= old_number {old_number}")
							PipelineStep.objects.filter(id=step.id).update(step_number = index)

					# Otherwise, we renumber from after where we've inserted the new step.
					else:
						print(f"Not an existing step. Renumber from where new step inserted @index=instance.step_number {step_number}")
						if index > instance.step_number:
							PipelineStep.objects.filter(id=step.id).update(step_number = index)

	else:
		instance.step_number=0


def renumber_pipeline_steps_on_delete(sender, instance, **kwargs):

	# IF there is a parent pipeline, check that we don't need to renumber other steps.
	if instance.parent_pipeline:
		pipelineSteps = PipelineStep.objects.filter(parent_pipeline=instance.parent_pipeline.id).all()

		numbered_steps = {}
		indexToRemove=-1

		for index, ps in enumerate(pipelineSteps):
			numbered_steps[ps.step_number]=ps

		numbered_steps_items = list(numbered_steps.items())

		for index, (step_number, step) in enumerate(numbered_steps_items):
			if step_number==instance.step_number:
				indexToRemove=step_number
				break

		if indexToRemove != -1:
			try:
				affected_steps = numbered_steps_items[indexToRemove+1:]
				for step_number, step in affected_steps:
					PipelineStep.objects.filter(id=step.id).update(step_number=step_number - 1)

			except:
				pass


def update_pipeline_schema(sender, instance, **kwargs):

	# If this pipeline step is part of a pipeline, then update the pipeline's schema (if not, nothing to do)
	if instance.parent_pipeline:

		pipeline = Pipeline.objects.get(id=instance.parent_pipeline.id)
		numbered_schemas = {}
		schema = []
		pipelineSteps = PipelineStep.objects.filter(parent_pipeline=instance.parent_pipeline.id).all()	# pipelineSteps =

		for index, ps in enumerate(pipelineSteps):
			try:
				numbered_schemas[index] = json.loads(ps.script.required_inputs)
			except Exception as e:
				numbered_schemas[index] = {}

		for i in range(0, len(pipelineSteps)):
			schema.append(numbered_schemas[i])

		# Need to add one as there's a built-in packaging step.
		# Packaging can take a while, so, if you don't add a step to the count
		# On the UI it looks like results are hanging. Completion goes to 100% while job is "stuck" running
		pipeline.total_steps = len(pipelineSteps) + 1
		pipeline.schema = json.dumps({"schema": schema})
		pipeline.save()

# When a new script is created... first install the required packages
def setup_python_script_on_create(sender, instance, created, **kwargs):
	if created:

		setupSteps = []

		# if there is a list of required packages, add a job to install them
		if not instance.required_packages == "":
			packages = instance.required_packages.splitlines()
			installPackages.delay(instance.id, *packages)

		if not instance.setup_script == "":
			lines = instance.setup_script.splitlines()
			runPythonScriptSetup.delay(instance.id, *lines)

		setupSteps.append(updatePythonPackage.si(instance.id))

		steps = len(setupSteps)
		if steps == 1:
			setupSteps[0].apply_async()
		elif steps > 1:
			chain(*setupSteps)()


# When a python script is updated... save the updated code and, if necessary, run the installer.
def update_python_script_on_save(sender, instance, **kwargs):

	try:
		obj = sender.objects.get(pk=instance.pk)
	except sender.DoesNotExist:
		pass
	else:
		# Required package field has changed, try to install new packages.
		if not obj.required_packages == instance.required_packages:
			print("Python script updated... running install script.")

			# if there is a list of required packages, add a job to install them
			if not instance.required_packages == "":
				packages = instance.required_packages.splitlines()
				installPackages.delay(instance.id, *packages)

		if not obj.setup_script == instance.setup_script:
			print("Install script updated... running install script.")

			if not instance.setup_script == "":
				lines = instance.setup_script.splitlines()
				runPythonScriptSetup.delay(instance.id, *lines)

		updatePythonPackage.delay(instance.id)

# When a python script is updated... delete the module from the modules dir
def remove_python_script_on_delete(sender, instance, **kwargs):
	print("Python script deleted... need to remove all modules and files.")
	print("Instance is: {0}".format(instance))
	setupSteps = []
	setupSteps.append(deletePythonPackage.si(instance.name))
	chain(*setupSteps).apply_async()

