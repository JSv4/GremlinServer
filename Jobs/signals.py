from celery import chain
import json
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
from .serializers import EdgeSerializer

from .tasks.task_helpers import buildNodePipelineRecursively
from .tasks.tasks import runJob, extractTextForDoc, \
    runScriptEnvVarInstaller, runScriptPackageInstaller, recalculatePipelineDigraph, unlockScript, lockScript, \
    runScriptSetupScript
from .models import PipelineNode, Pipeline, PythonScript, Edge

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# This is how jobs are currently queued... seems to be robust. If a job is switched from not queued to queued (and the
# job hasn't already started, errored out or finished), add runJob task to celery queue for execution.
def run_job_on_queued(sender, instance, created, **kwargs):
    if instance.queued and not instance.started and not instance.error and not instance.finished:
        runJob.delay(jobId=instance.id)

# When doc is created, try to extact text using Tika.
# Need to make this atomic to avoid a race condition with remote, S3 storage.
# https://stackoverflow.com/questions/53503460/possible-race-condition-between-django-post-save-signal-and-celery-task
# https://stackoverflow.com/questions/45276828/handle-post-save-signal-in-celery
def process_doc_on_create_atomic(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: extractTextForDoc.delay(docId=instance.id))


# When a new script is created... perform required setup (if there are values that require setup)
def setup_python_script_on_create(sender, instance, created, **kwargs):

    if created and not instance.locked:

        setup_steps=[]

        # Determine which setup tasks are required based on what has changed about the script. Assemble a chain of
        # setup scripts with unlock as the terminator.

        # if there is a list of required packages, add a job to install them
        if not instance.required_packages == "":
            setup_steps.append(runScriptPackageInstaller.s(scriptId=instance.id))

        if not instance.setup_script == "":
            setup_steps.append(runScriptSetupScript.s(scriptId=instance.id))

        if not instance.env_variables == "":
            setup_steps.append(runScriptEnvVarInstaller.s(scriptId=instance.id))

        # If no setup steps were required, don't bother with lock, unlock.
        if len(setup_steps)>0:
            logger.info("Detected that script setup tasks are needed. Lock.")
            setup_steps.insert(0, lockScript.si(scriptId=instance.id))
            setup_steps.append(unlockScript.s(scriptId=instance.id))
            chain(setup_steps).apply_async()
        else:
            logger.info("Detected no setup tasks required. No lock or unlock required.")


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
                print(f"Setup script updated AND new script is not blank. New value: {instance.setup_script}")
                celery_jobs.append(runScriptSetupScript.s(scriptId=instance.id,
                                                          setup_script=instance.setup_script))

            if orig.env_variables != instance.env_variables and instance.env_variables != "":
                print("Env variables updated AND new variables are not blank")
                celery_jobs.append(runScriptEnvVarInstaller.s(scriptId=instance.id,
                                                                  env_variables=instance.env_variables))

            if len(celery_jobs) > 0:

                logger.info("Detected that script setup tasks are needed. Tasks:")
                celery_jobs.insert(0, lockScript.si(scriptId=instance.id))
                celery_jobs.append(unlockScript.s(scriptId=instance.id))
                logger.info(celery_jobs)
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
