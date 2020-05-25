from django.apps import AppConfig
from django.db.models.signals import post_save, pre_delete, post_delete, pre_save

class JobsConfig(AppConfig):
    name = 'Jobs'

    #importing signals here per
    # official celery docs:
    # https://docs.djangoproject.com/en/3.0/topics/signals/
    # and, this excellent guide:
    # https://simpleisbetterthancomplex.com/tutorial/2016/07/28/how-to-create-django-signals.html
    def ready(self):

        from .signals import run_job_on_queued, process_doc_on_create, setup_python_script_on_create, \
            update_python_script_on_save, remove_python_script_on_delete, update_pipeline_schema, \
            renumber_pipeline_steps_on_delete, renumber_pipeline_steps_on_create_or_update
        from .models import Job, Document, PythonScript, PipelineStep

        # After a pipeline step is deleted, regenerate the schema for the pipeline
        post_delete.connect(update_pipeline_schema, sender=PipelineStep,
                            dispatch_uid="update_pipeline_schema_on_delete")

        # After a pipeline step is deleted, renumber all subsequent pipeline steps in that pipeline
        pre_delete.connect(renumber_pipeline_steps_on_delete, sender=PipelineStep,
                           dispatch_uid="renumber_pipeline_steps_on_delete")

        # Before committing a pipeline step to db, renumber other steps linked to same pipeline
        pre_save.connect(renumber_pipeline_steps_on_create_or_update, sender=PipelineStep,
                         dispatch_uid="renumber_pipeline_steps_on_create_or_update")

        # After a pipeline step is saved / updated, regenerate the schema for the linked pipeline (if applicable)
        post_save.connect(update_pipeline_schema, sender=PipelineStep,
                          dispatch_uid="update_pipeline_schema_on_save")

        # This is how jobs are launched. If we detect that a job is switched from queued = false to queued = true, run job.
        post_save.connect(run_job_on_queued, sender=Job, dispatch_uid="run_job_on_queued")

        # When a new doc is created, queue a text extract job
        post_save.connect(process_doc_on_create, sender=Document, dispatch_uid="process_doc_on_create")

        #When a python script is created, run installer task for that script
        post_save.connect(setup_python_script_on_create, sender=PythonScript,
                          dispatch_uid="install_packages_on_create")

        # Right before a python script is UPDATED, see if the package list has changed and, if so, run the installer task.
        pre_save.connect(update_python_script_on_save, sender=PythonScript,
                         dispatch_uid="update_python_script_on_save")

        # If the Python Script obj is deleted in the database, delete the package on the running instance of Gremlin.
        pre_delete.connect(remove_python_script_on_delete, sender=PythonScript,
                           dispatch_uid="remove_python_script_on_delete")
