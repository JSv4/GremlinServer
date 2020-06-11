from celery import chain
import json
import operator
from django.db import transaction

from .tasks.tasks import runJob, installPackages, runPythonScriptSetup, extractTextForDoc, runScriptInstalls
from .models import PipelineStep, Pipeline, PythonScript

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def run_job_on_queued(sender, instance, created, **kwargs):
    if instance.queued and not instance.started and not instance.error and not instance.finished:
        runJob.delay(jobId=instance.id)


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
            instance.step_number = stepCount  # Think this should be stepCount - 1. Wait actually don't think so because that's the count without new step.

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
                    print(filter(lambda step: step.id == instance.id, pipelineSteps))
                    old_number = list(filter(lambda step: step.id == instance.id, pipelineSteps))[0].step_number
                    print(f"This was an pre-existing step, old step_number is {old_number}")
                except Exception as e:
                    print(f"ERROR fetching old pipelineStep step_number: {e}")

            print("You chose to drop this in the middle of the existing pipeline...")

            stepList = []

            # build a list of the steps held in tuples, with step_number, step pairs
            print("Current pipelineSteps:")
            for index, step in enumerate(pipelineSteps):
                print(f"Step #{step.step_number}: {step}")
                if step.id is not instance.id:
                    stepList.append((step.step_number, step))

            # sort the list
            stepList.sort(key=operator.itemgetter(0))
            print(f"sorted stepList: {stepList}")

            # insert the new instance where it's supposed to go. This is post sort. Don't resort.
            stepList.insert(instance.step_number, (instance.step_number, instance))

            # now traverse the sorted list, start renumbering using new indices at one of two spots depending
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
                            PipelineStep.objects.filter(id=step.id).update(step_number=index)

                    # Otherwise, we renumber from after where we've inserted the new step.
                    else:
                        print(
                            f"Not an existing step. Renumber from where new step inserted @index=instance.step_number {step_number}")
                        if index > instance.step_number:
                            PipelineStep.objects.filter(id=step.id).update(step_number=index)

    else:
        instance.step_number = 0


def renumber_pipeline_steps_on_delete(sender, instance, **kwargs):
    # IF there is a parent pipeline, check that we don't need to renumber other steps.
    if instance.parent_pipeline:
        pipelineSteps = PipelineStep.objects.filter(parent_pipeline=instance.parent_pipeline.id).all()

        numbered_steps = {}
        indexToRemove = -1

        for index, ps in enumerate(pipelineSteps):
            numbered_steps[ps.step_number] = ps

        numbered_steps_items = list(numbered_steps.items())

        for index, (step_number, step) in enumerate(numbered_steps_items):
            if step_number == instance.step_number:
                indexToRemove = step_number
                break

        if indexToRemove != -1:
            try:
                affected_steps = numbered_steps_items[indexToRemove + 1:]
                for step_number, step in affected_steps:
                    PipelineStep.objects.filter(id=step.id).update(step_number=step_number - 1)

            except:
                pass


# Updates the pipeline schema and the pipeline supported files when one of the linked scripts changes...
# I am doing this to avoid complicated recalculatings at runtime... that said, it's possible that trying to compute
# this on the backend in response to changes could lead to data getting out of sync... Can trying to remedy this later
# if it becomes an issue.
def update_pipeline_schema(sender, instance, **kwargs):
    print(f"Got signal to update pipeline schema for sender type {sender} and instance ID #{instance.id}. "
                f"kwargs are {kwargs}")
    try:
        if sender is PipelineStep:
            print("Sender is PipelineStep")
            pipeline = Pipeline.objects.filter(id=instance.parent_pipeline.id)
            if pipeline.count() == 1:
                pipelines = [*pipeline]
        # If the sender is a PythonScript... get any Pipeline that uses the script (as well as any PipelineSteps)
        # Then we need to regenerate the supported filetypes and schemas for those objs.
        elif sender is PythonScript:
            print("Sender is PythonScript")
            script = PythonScript.objects.get(id=instance.id)

            # Scripts have a lot of different settings and we don't want to have to constantly run the expensve recalculations
            # on the Pipeline and PipelineSteps for *every* script *every* time it changes. Check here to make sure that
            # the script schema or its supported file types have changed.
            # with pre-save, you can tell if an object already exists by seeing if the instance in question has an id
            if instance.id:
                print("PythonScript already exists")
                oldInstance = PythonScript.objects.get(id=instance.id)

                # If the supported_file_type and required_inputs (should be renamed schema) fields are the same from old obj
                # to new, don't do anything further.
                if (instance.supported_file_types == oldInstance.supported_file_types and
                    instance.required_inputs == oldInstance.required_inputs):
                    print("No changes! No nothing.")
                    return None

                print("Changes detected!")

            else:
                return None  # If this is a new script, obv we don't need to recalculate any pipelines or pipeline steps

            print("Get pipelineSteps and Pipelines")

            pipelineStepIds = PipelineStep.objects.prefetch_related('parent_pipeline').filter(script=script) \
                .exclude(parent_pipeline__isnull=True).values_list('parent_pipeline__id')
            print("pipelineStepIds:")
            print(pipelineStepIds)

            pipelines = Pipeline.objects.filter(id__in=pipelineStepIds)
            print("pipelines")
            print(pipelines)

        else:
            print(f"Unexpected sender type of {type(sender)} received by update_pipeline_schema")
            return None

        if len(pipelines) > 0:

            for pipeline in pipelines:

                print(f"Rebuild schemas and allowed files for pipeline {pipeline}")
                numbered_schemas = {}
                schema = []
                supported_files = []
                pipelineSteps = PipelineStep.objects.filter(
                    parent_pipeline=pipeline).all()
                print(f"pipelineSteps: {pipelineSteps}")

                for index, ps in enumerate(pipelineSteps):
                    try:
                        numbered_schemas[index] = json.loads(ps.script.required_inputs)
                    except Exception as e:
                        print(f"Error trying to aggregate schema for script {ps.id} in pipeline {pipeline.id}")
                        numbered_schemas[index] = {}

                    try:
                        files = json.loads(ps.script.supported_file_types)
                        if len(supported_files) == 0:
                            supported_files = [*files]
                        else:
                            supported_files = [x for x in supported_files if x in files]
                    except Exception as e:
                        print(
                            f"Error trying to aggregate supported files for script {ps.id} in pipeline {pipeline.id}")

                for i in range(0, len(pipelineSteps)):
                    schema.append(numbered_schemas[i])

                # Need to add one as there's a built-in packaging step.
                # Packaging can take a while, so, if you don't add a step to the count
                # On the UI it looks like results are hanging. Completion goes to 100% while job is "stuck" running
                pipeline.total_steps = len(pipelineSteps) + 1
                pipeline.schema = json.dumps({"schema": schema})
                pipeline.supported_files = json.dumps({"supported_files": supported_files})
                pipeline.save()

    except Exception as e:
        print(f"Error trying to update pipeline schema: {e}")


# When a new script is created... first install the required packages
def setup_python_script_on_create(sender, instance, created, **kwargs):
    runScriptInstalls.s(scriptId=instance.id)


# When a python script is updated... save the updated code and, if necessary, run the installer.
def update_python_script_on_save(sender, instance, **kwargs):
    runScriptInstalls.s(scriptId=instance.id)
