import uuid
from django.apps import AppConfig
from django.db.models.signals import post_save, post_delete, pre_save

class JobsConfig(AppConfig):
    name = 'Jobs'

    #importing signals here per
    # official celery docs:
    # https://docs.djangoproject.com/en/3.0/topics/signals/
    # and, this excellent guide:
    # https://simpleisbetterthancomplex.com/tutorial/2016/07/28/how-to-create-django-signals.html
    def ready(self):

        from .signals import run_job_on_queued, setup_python_script_on_create, \
            update_python_script_on_save, process_doc_on_create_atomic, \
            update_digraph_on_edge_change, update_digraph_on_node_create, \
            update_digraph_on_node_delete
        from .models import Job, Document, PythonScript, Edge, PipelineNode

        ########################### EDGE SIGNALS ###########################

        # After a pipeline edge is deleted, regenerate the pipeline digraph.
        post_delete.connect(update_digraph_on_edge_change, sender=Edge,
                            dispatch_uid=uuid.uuid4())

        # After a pipeline edge is saved / updated, regenerate the pipeline digraph.
        post_save.connect(update_digraph_on_edge_change, sender=Edge,
                          dispatch_uid=uuid.uuid4())

        ########################### NODE SIGNALS ###########################

        # After a pipeline step is created, regenerate the linked digraph (we don't care about edits as node meta data
        # should be fetched separately and the digraph should just show the ids and relationships to each other in
        # the digraph). As long as the nodes and relationships thereto remain unchanged, don't care about any other
        # node props or linked scripts.
        post_save.connect(update_digraph_on_node_create, sender=PipelineNode,
                          dispatch_uid=uuid.uuid4())

        # After a pipeline step is deleted, regenerate the linked digraph (as with post_save, we don't care about node
        # meta data.
        post_delete.connect(update_digraph_on_node_delete, sender=PipelineNode,
                            dispatch_uid=uuid.uuid4())

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

        #When a python script is created, run installer task for that script
        post_save.connect(setup_python_script_on_create, sender=PythonScript,
                          dispatch_uid=uuid.uuid4())

        # Right before a python script is UPDATED, see if the package list has changed and,
        # if so, run the installer task.
        pre_save.connect(update_python_script_on_save, sender=PythonScript,
                         dispatch_uid=uuid.uuid4())
