from celery import chain
import json
from django.db import transaction

from .tasks.task_helpers import buildNodePipelineRecursively
from .tasks.tasks import runJob, runPythonScriptSetup, extractTextForDoc, \
    runScriptEnvVarInstaller, runScriptPackageInstaller, recalculatePipelineDigraph, unlockScript
from .models import PipelineNode, Pipeline, PythonScript, Edge

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
        transaction.on_commit(lambda: extractTextForDoc.delay(docId=instance.id))


# Updates the pipeline schema and the pipeline supported files when one of the linked scripts changes...
# I am doing this to avoid complicated recalculations at runtime... that said, it's possible that trying to compute
# this on the backend in response to changes could lead to data getting out of sync... Can trying to remedy this later
# if it becomes an issue.
def update_pipeline_schema(sender, instance, **kwargs):
    print(f"Got signal to update pipeline schema for sender type {sender} and instance ID #{instance.id}. "
          f"kwargs are {kwargs}")

    try:

        if sender is Edge and not sender.parent_pipeline.locked if sender.parent_pipeline else False:
            print("Sender is Pipeline Digraph Edge")
            pipeline = Pipeline.objects.filter(id=instance.parent_pipeline.id)
            if pipeline.count() == 1:
                pipelines = [*pipeline]

        # If the sender is a PythonScript... get any Pipeline that uses the script (as well as any PipelineSteps)
        # Then we need to regenerate the supported filetypes and schemas for those objs.
        elif sender is PythonScript and not sender.locked:

            print("Sender is PythonScript")

            # Scripts have a lot of different settings and we don't want to have to constantly run the expensve recalculations
            # on the Pipeline and PipelineSteps for *every* script *every* time it changes. Check here to make sure that
            # the script schema or its supported file types have changed.
            # with pre-save, you can tell if an object already exists by seeing if the instance in question has an id
            if instance.id:

                script = PythonScript.objects.get(id=instance.id)
                oldInstance = PythonScript.objects.get(id=instance.id)

                print("PythonScript already exists")

                # If the supported_file_type and required_inputs (should be renamed schema) fields are the same from old obj
                # to new, don't do anything further.
                if (instance.supported_file_types == oldInstance.supported_file_types and
                    instance.required_inputs == oldInstance.required_inputs):
                    print("No changes! Do nothing...")
                    return None

                print("Changes detected!")

            else:
                return None  # If this is a new script, obv we don't need to recalculate any pipelines or pipeline steps

            print("Get pipelineSteps and Pipelines")

            pipelineStepIds = PipelineNode.objects.prefetch_related('parent_pipeline').filter(script=script) \
                .exclude(parent_pipeline__isnull=True).values_list('parent_pipeline__id')
            print("pipelineStepIds:")
            print(pipelineStepIds)

            pipelines = Pipeline.objects.filter(id__in=pipelineStepIds)
            print("pipelines")
            print(pipelines)

        else:
            print(f"Unexpected sender type of {type(sender)} received by update_pipeline_schema")
            return None

        print(f"Number of affected pipelines to rebuild schemas for: {len(pipelines)}")
        if len(pipelines) > 0:

            print(f"Pipelines: {pipelines}")

            for pipeline_num, pipeline in enumerate(pipelines):

                print(f"Pipeline {pipeline_num} of {len(pipelines) + 1}: Rebuild schemas and "
                      f"allowed files for pipeline {pipeline}")

                numbered_schemas = {}
                supported_files = []

                # If there is no root node, we can't build the schema and there's nothing to do here.
                if pipeline.root_node:

                    pipelineNodes = buildNodePipelineRecursively(pipeline, node=pipeline.root_node)

                    for index, ps in enumerate(pipelineNodes):
                        schema = {}

                        try:
                            schema = json.loads(ps.script.schema)
                        except Exception as e:
                            print(f"Error trying to fetch schema for script {ps.id} in pipeline {pipeline.id}: {e}")

                        numbered_schemas[ps.id] = {
                            "name": ps.name,
                            "schema": schema
                        }

                        try:
                            files = json.loads(ps.script.supported_file_types)
                            if len(supported_files) == 0:
                                supported_files = [*files]
                            else:
                                supported_files = [x for x in supported_files if x in files]
                        except Exception as e:
                            print(
                                f"Error trying to aggregate supported files for script {ps.id} in pipeline {pipeline.id}")

                else:
                    pipelineNodes = []
                    numbered_schemas = {}
                    supported_files = []

                # Need to add one as there's a built-in packaging step.
                # Packaging can take a while, so, if you don't add a step to the count
                # On the UI it looks like results are hanging. Completion goes to 100% while job is "stuck" running
                pipeline.total_steps = len(pipelineNodes) + 1
                pipeline.schema = json.dumps({"schema": numbered_schemas})
                pipeline.supported_files = json.dumps({"supported_files": supported_files})
                pipeline.save()

    except Exception as e:
        print(f"Error trying to update pipeline schema: {e}")


# When a new script is created... perform required setup (if there are values that require setup)
def setup_python_script_on_create(sender, instance, created, **kwargs):
    if created and not instance.locked:

        instance.locked = True
        instance.save()

        # if there is a list of required packages, add a job to install them
        if not instance.required_packages == "":
            runScriptPackageInstaller.delay(scriptId=instance.id)

        if not instance.setup_script == "":
            runPythonScriptSetup.delay(scriptId=instance.id)

        if not instance.env_variables == "":
            runScriptEnvVarInstaller.delay(scriptId=instance.id)

        instance.locked = False
        instance.save()


# When a python script is updated... save the updated code and, if necessary, run the installer.
def update_python_script_on_save(sender, instance, **kwargs):
    # print("Got request to update_python_script_on_save")
    try:
        if not instance.locked:
            orig = sender.objects.get(pk=instance.pk)

            celery_jobs = []

            if orig.required_packages != instance.required_packages and instance.required_packages != "":
                print("Required packages updated AND new package list is not blank")
                celery_jobs.append(runScriptPackageInstaller.s(scriptId=instance.id,
                                                               new_packages=instance.required_packages))

            if orig.setup_script != instance.setup_script and instance.setup_script != "":
                print("Setup script updated AND new script is not blank")
                celery_jobs.append(runPythonScriptSetup.s(scriptId=instance.id,
                                                          setup_script=instance.setup_script))

            if orig.env_variables != instance.env_variables and instance.env_variables != "":
                print("Env variables updated AND new variables are not blank")
                celery_jobs.append(runScriptEnvVarInstaller.delay(scriptId=instance.id,
                                                                  env_variables=instance.env_variables))

            if len(celery_jobs) > 0:

                print("There are long-running installer tasks:")
                print(celery_jobs)

                celery_jobs.append(unlockScript.s(scriptId=instance.id))
                chain(celery_jobs).apply_async()

        else:
            print(f"This most current version script ID {instance.id} is locked. DO NOT RUN SETUP.")

    except sender.DoesNotExist:
        pass


# When a digraph edge is updated... rerender the digraph property... which is a react flowchart compatible JSON structure
# That shows the digraph structure of the job... everything is keyed off of it.
# TODO - what happens if you try to edit multiple nodes at the same time? THIS IS NOT ALLOWED. SIMPLE
# Django is synchronous by nature. Don't screw with this. If you must, choose another framework.
def update_digraph_on_edge_change(sender, instance, **kwargs):
    if not instance.parent_pipeline.locked if instance.parent_pipeline else False:
        recalculatePipelineDigraph.delay(pipelineId=instance.parent_pipeline.id)  # TODO - make sure
    else:
        print(f"Detected change on edge {instance.id} yet its parent pipeline is LOCKED. Do nothing.")


# When a node is created... rerender the parent_pipeline digraph property... e
# That shows the digraph structure of the job... everything is keyed off of it.
def update_digraph_on_node_create(sender, instance, created, **kwargs):
    if created and not instance.parent_pipeline.locked if instance.parent_pipeline else False:
        print("Node was created... try to update parent_pipeline digraph")
        recalculatePipelineDigraph.delay(pipelineId=instance.parent_pipeline.id)


# When a node is deleted... rerender the parent_pipeline digraph property... e
# That shows the digraph structure of the job... everything is keyed off of it.
def update_digraph_on_node_delete(sender, instance, **kwargs):
    print("Node was deleted... try to update parent_pipeline digraph")
    recalculatePipelineDigraph.delay(pipelineId=instance.parent_pipeline.id)
