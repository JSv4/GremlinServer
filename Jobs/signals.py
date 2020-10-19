from celery import chain
import json
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .serializers import EdgeSerializer

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

    print(f"update_digraph_on_edge_change - sender type {type(sender)} instance is: {instance}")
    print(EdgeSerializer(instance).data)

    try:
        pipeline = Pipeline.objects.get(pk=instance.parent_pipeline_id)
        if pipeline and not pipeline.locked:
            recalculatePipelineDigraph.delay(pipelineId=instance.parent_pipeline.id)
        else:
            print(f"Detected change on edge {instance.id} yet its parent pipeline is LOCKED. Do nothing.")

    except ObjectDoesNotExist as e:
        print(f"Can't update pipeline on edge delete: {e}.\nThis is a sign digraph update was called in process of deleting a pipeline.")

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
