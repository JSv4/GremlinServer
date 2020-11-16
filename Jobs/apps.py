import uuid
from django.apps import AppConfig
from django.db.models.signals import post_save, post_delete, pre_save

class JobsConfig(AppConfig):
    name = 'Jobs'

    # SIGNALS to trigger long-running tasks on certain DB changes
    #
    # official celery docs:
    # https://docs.djangoproject.com/en/3.0/topics/signals/
    # and, this excellent guide:
    # https://simpleisbetterthancomplex.com/tutorial/2016/07/28/how-to-create-django-signals.html
    def ready(self):

        from .signals import run_job_on_queued, setup_python_script_after_save, \
            process_doc_on_create_atomic
        from .models import Job, Document, PythonScript

        ########################### JOB SIGNALS ###########################

        # This is how jobs are launched. If we detect that a job is switched from
        # queued = false to queued = true, run job.
        post_save.connect(run_job_on_queued, sender=Job,
                          dispatch_uid=uuid.uuid4())

        ########################### DOCUMENT SIGNALS ###########################

        # When a new doc is created, queue a text extract job
        #post_save.connect(process_doc_on_create, sender=Document, dispatch_uid="process_doc_on_create")
        post_save.connect(process_doc_on_create_atomic, sender=Document,
                          dispatch_uid=uuid.uuid4())

        ########################### PYTHON SCRIPT SIGNALS ###########################

        # When a python script is saved, flags are created to install various features (packages, install script or env
        # variables). This signal checks for the flags and queus up long-running, async tasks to handle them.
        post_save.connect(setup_python_script_after_save, sender=PythonScript,
                          dispatch_uid=uuid.uuid4())
