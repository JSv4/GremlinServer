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
def setup_python_script_after_save(sender, instance, created, **kwargs):

    setup_steps = []

    if instance.package_needs_install:
        logger.info("setup_python_script_after_save - Required packages updated AND new package list is not blank")
        setup_steps.append(runScriptPackageInstaller.s(scriptId=instance.id,
                                                       new_packages=instance.required_packages))

    if instance.script_needs_install:
        logger.info(f"setup_python_script_after_save - Setup script updated AND new script is not blank. New value: {instance.setup_script}")
        setup_steps.append(runScriptSetupScript.s(scriptId=instance.id,
                                                  setup_script=instance.setup_script))

    if instance.env_variables_need_install:
        logger.info("setup_python_script_after_save - Env variables updated AND new variables are not blank")
        setup_steps.append(runScriptEnvVarInstaller.s(scriptId=instance.id,
                                                      env_variables=instance.env_variables))

    if len(setup_steps) > 0:
        logger.info("setup_python_script_after_save - Detected that script setup tasks are needed. Tasks:")
        setup_steps.append(unlockScript.s(scriptId=instance.id))
        logger.info(setup_steps)
        chain(setup_steps).apply_async()

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
