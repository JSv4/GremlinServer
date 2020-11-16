from celery import chain
from django.db import transaction
from .serializers import PythonScriptSerializer

from .tasks.tasks import runJob, extractTextForDoc, \
    runScriptEnvVarInstaller, runScriptPackageInstaller, unlockScript, lockScript, \
    runScriptSetupScript

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

    print(f"After save script, model is: {PythonScriptSerializer(instance).data}")

    if not instance.locked:

        setup_steps = []

        if instance.package_needs_install:
            logger.info("setup_python_script_after_save - Required packages updated AND new package list is not blank")
            setup_steps.append(runScriptPackageInstaller.s(scriptId=instance.id))

        if instance.script_needs_install:
            logger.info(f"setup_python_script_after_save - Setup script updated AND new script is not blank. New value: {instance.setup_script}")
            setup_steps.append(runScriptSetupScript.s(scriptId=instance.id))

        if instance.env_variables_need_install:
            logger.info("setup_python_script_after_save - Env variables updated AND new variables are not blank")
            setup_steps.append(runScriptEnvVarInstaller.s(scriptId=instance.id))

        if len(setup_steps) > 0:
            logger.info("setup_python_script_after_save - Detected that script setup tasks are needed. Tasks:")
            setup_steps.insert(0, lockScript.s(scriptId=instance.id))
            setup_steps.append(unlockScript.s(scriptId=instance.id, installer=True))
            logger.info(setup_steps)
            transaction.on_commit(lambda: chain(setup_steps).apply_async()) #if we don't do this, looks like unlock was getting pre-save version of model, then saving that over actual "new" values.
