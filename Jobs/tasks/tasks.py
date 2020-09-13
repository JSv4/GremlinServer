from __future__ import absolute_import, unicode_literals

import requests
import zipfile
import traceback
import tempfile
from pathlib import Path
from glob import iglob
from os import remove
from errno import ENOENT
from zipfile import ZipFile
from django.core.files.base import ContentFile
from django.db import connection

from config import celery_app
from ..serializers import PythonScriptSummarySerializer
from ..models import Job, Document, PipelineNode, Result, PythonScript, Edge, Pipeline
from celery import chain, group, chord
from celery.signals import celeryd_after_setup
from .task_helpers import exec_with_return, returnScriptMethod, buildScriptInput, \
    transformStepInputs, createFunctionFromString, buildNodePipelineRecursively, getPrecedingResults
from .taskLoggers import JobLogger, TaskLogger
from shutil import copyfileobj, rmtree
from django.conf import settings
from datetime import datetime
import subprocess
import sys
from io import StringIO  # Python 3
import celery
import codecs
import os
import io
import docx2txt
import uuid
import json
import time
import jsonschema

# Errors
class Error(Exception):
    """Base class for exceptions in this module."""
    pass

class FileNotSupportedError(Error):
    """Exception raised for unsupported file input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message

class FileInputError(Error):
    """Exception raised for errors in the file input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class DataInputError(Error):
    """Exception raised for errors in the data input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message

class UserScriptError(Error):
    """Raised when User's script fails.

   Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


class PrecedingNodeError(Error):
    """Raised when previous step in a pipeline fails.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message

class JobAlreadyFinishedError(Error):
    """Raised when somehow node is running but job is done. Not sure this can actually happen unless DB corrupted.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message

class UserScriptError(Error):
    """Raised when user script fails.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message

class PipelineError(Error):
    """Raised when user script fails.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message

# Tika Extraction Imports
import tika  # python wrapper for tika server

tika.initVM()  # initialize tika object
from tika import \
    parser  # then import parser. It's only being used for .doc ATM as I haven't found another good solution for .doc extract

# make default django storage available
from django.core.files.storage import default_storage

# import gremlin task constants (for job return values)
from .task_constants import JOB_FAILED_DID_NOT_FINISH, \
    JOB_FAILED_INVALID_DOC_ID, JOB_FAILED_INVALID_JOB_ID, JOB_SUCCESS, \
    JOB_FAILED_UNSUPPORTED_FILE_TYPE, JOB_FAILED_INVALID_INPUTS

# task helper methods
from .task_helpers import stopJob, jobSucceeded, saveTaskFile, ScriptLogger

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
step_logger = logging.getLogger('task_db')
job_logger = logging.getLogger('job_db')


# Cleanup for temporary files
def cleanup(temp_name):
    for filename in iglob(temp_name + '*' if temp_name else temp_name):
        try:
            remove(filename)
        except OSError as e:
            if e.errno != ENOENT:
                raise e


# One of the challenges of switching to a docker-based deploy is that system env isn't persisted and
# The whole goal of this system is to dynamically provision and reprovision scripts into a data processing
# pipeline. Sooo.... current workaround (to increase performance on *script* run is to preprocess all of the setup
# on startup. Currently the approach is super naive. Doesn't do any checking to see if this is necessary so could be duplicative
@celeryd_after_setup.connect
def setup_direct_queue(sender, instance, **kwargs):
    logging.info(f"Celery worker is up.\nSender:{sender}.\nInstance:\n {instance}")

    try:
        scripts = PythonScript.objects.all()

        # For each pythonScript, run the setup code...
        for pythonScript in scripts:

            packages = pythonScript.required_packages.split("\n")
            if len(packages) > 0:
                logging.info(f"Script requires {len(packages)} packages. "
                             f"Ensure required packages are installed:\n {pythonScript.required_packages}")

                p = subprocess.Popen([sys.executable, "-m", "pip", "install", *packages], stdout=subprocess.PIPE)
                out, err = p.communicate()

                # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
                out = codecs.getdecoder("unicode_escape")(out)[0]
                if err:
                    err = codecs.getdecoder("unicode_escape")(err)[0]
                    logging.error(f"Errors from pythonScript pre check: \n{err}")

                logging.info(f"Results of python installer for {pythonScript.name} \n{out}")

            setupScript = pythonScript.setup_script
            if setupScript != "":

                logging.info(f"Script {pythonScript.name} has setupScript: {setupScript}")

                lines = setupScript.split("\n")

                for line in lines:

                    p = subprocess.Popen(line.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, err = p.communicate()

                    # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
                    out = codecs.getdecoder("unicode_escape")(out)[0]
                    if err:
                        err = codecs.getdecoder("unicode_escape")(err)[0]
                        logging.error(f"Errors from pythonScript pre check: \n{err}")

                    logging.info(f"Results of bash install pythonScript for {pythonScript.name}: \n{out}")

            envVariables = pythonScript.env_variables
            if envVariables != "":
                logging.info(f"It appears there are env variables: {envVariables}")

                vars = {}
                try:
                    vars = json.loads(envVariables)
                    logging.info(f"Parsed following env var structure: {vars}")
                    logging.info(f"Var type is: {type(vars)}")
                except:
                    logging.warning("Unable to parse env variables.")
                    pass

                for e, v in vars.items():
                    logging.info(f"Adding env_var {e} with value {v}")
                    os.environ[e] = v

    except Exception as e:
        logging.error(f"Error setting up celery worker on celeryd_init.\nSender:{sender}.\n"
                      f"Instance:\n {instance} \nError: \n{e}")


class FaultTolerantTask(celery.Task):
    """ Implements after return hook to close the invalid connection.
    This way, django is forced to serve a new connection for the next
    task.
    """
    abstract = True

    def after_return(self, *args, **kwargs):
        connection.close()


@celery_app.task(base=FaultTolerantTask, name="Run Script Package Installer")
def runScriptPackageInstaller(*args, scriptId=-1, **kwargs):
    try:
        pythonScript = PythonScript.objects.get(id=scriptId)

        packages = pythonScript.required_packages.split("\n")
        if len(packages) > 0:
            logging.info(f"Script requires {len(packages)} packages. "
                         f"Ensure required packages are installed:\n {pythonScript.required_packages}")

            p = subprocess.Popen([sys.executable, "-m", "pip", "install", *packages], stdout=subprocess.PIPE)
            out, err = p.communicate()

            # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
            out = codecs.getdecoder("unicode_escape")(out)[0]
            if err:
                err = codecs.getdecoder("unicode_escape")(err)[0]
                logging.error(f"Errors from pythonScript pre check: \n{err}")

            logging.info(f"Results of python installer for {pythonScript.name} \n{out}")

    except Exception as e:
        logging.error(f"Error setting running python script installers.\nScript ID:{scriptId}.\n"
                      f"Error: \n{e}")


@celery_app.task(base=FaultTolerantTask, name="Run Script Setup Script Installer")
def runScriptSetupScript(*args, scriptId=-1, **kwargs):

    try:

        pythonScript = PythonScript.objects.get(id=scriptId)

        setupScript = pythonScript.setup_script
        if setupScript != "":

            logging.info(f"Script {pythonScript.name} has setupScript: {setupScript}")

            lines = setupScript.split("\n")

            for line in lines:

                p = subprocess.Popen(line.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = p.communicate()

                # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
                out = codecs.getdecoder("unicode_escape")(out)[0]
                if err:
                    err = codecs.getdecoder("unicode_escape")(err)[0]
                    logging.error(f"Errors from pythonScript pre check: \n{err}")

                logging.info(f"Results of bash install pythonScript for {pythonScript.name}: \n{out}")

    except Exception as e:
        logging.error(f"Error setting running python script installers.\nScript ID:{scriptId}.\n"
                      f"Error: \n{e}")


@celery_app.task(base=FaultTolerantTask, name="Run Script Env Variable Installer")
def runScriptEnvVarIntaller(*args, scriptId=-1, **kwargs):
    try:
        pythonScript = PythonScript.objects.get(id=scriptId)

        envVariables = pythonScript.env_variables
        if envVariables != "":
            logging.info(f"It appears there are env variables: {envVariables}")

            vars = {}
            try:
                vars = json.loads(envVariables)
                logging.info(f"Parsed following env var structure: {vars}")
                logging.info(f"Var type is: {type(vars)}")
            except:
                logging.warning("Unable to parse env variables.")
                pass

            for e, v in vars.items():
                logging.info(f"Adding env_var {e} with value {v}")
                os.environ[e] = v

    except Exception as e:
        logging.error(f"Error setting running python script installers.\nScript ID:{scriptId}.\n"
                      f"Error: \n{e}")


# Rather than tie up the main Django thread calculating a digraph,move it to a separate tasks that can be called
# from the on_save signal for the pipeline or the
@celery_app.task(base=FaultTolerantTask, name="Calculate digraph")
def recalculatePipelineDigraph(*args, pipelineId=-1, **kwargs):

    print("Recalculate Pipeline Digraph")

    try:
        nodes = PipelineNode.objects.prefetch_related('out_edges', 'in_edges').filter(parent_pipeline__id=pipelineId)
        edges = Edge.objects.filter(parent_pipeline__id=pipelineId)
        pipeline = Pipeline.objects.get(pk=pipelineId)

        digraph = {
            "offset": {
                "x": pipeline.x_offset,
                "y": pipeline.y_offset,
            },
            "type": ["PIPELINE"],
            "scale": pipeline.scale,
            "selected": {},
            "hovered": {},
        }
        renderedNodes = {}
        renderedEdges = {}

        for node in nodes:

            ports = {}

            if node.type == PipelineNode.SCRIPT:
                ports = {
                    "output": {
                        "id": 'output',
                        "type": 'output',
                    },
                    "input": {
                        "id": 'input',
                        "type": 'input',
                    },
                }
            elif node.type == PipelineNode.ROOT_NODE:
                ports = {
                    "output": {
                        "id": 'output',
                        "type": 'output',
                    },
                }
            # TODO - handle more node types

            print("Try to render node")
            print(f"Node: {node}")
            renderedNode = {
                "id": f"{node.id}",
                "name": node.name,
                "settings": node.step_settings,
                "input_transform": node.input_transform,
                "type": node.type,
                "position": {
                    "x": node.x_coord,
                    "y": node.y_coord
                },
                "ports": ports
            }

            # Only need to handle instances where script is null (e.g. where the node is a root node and there's
            # no linked script because it's hard coded on the backend
            if node.type == "ROOT_NODE":
                # If the default pre-processor has been overwritten... use linked script details
                if node.script == None:
                    renderedNode["script"] = {
                        "id": -1,
                        "human_name": "Pre Processor",
                        "type": "RUN_ON_JOB_DOCS",
                        "supported_file_types": "",
                        "description": "Default pre-processor to ensure docx, doc and pdf files are extracted."
                    }
                # otherwise... provide default values
                else:
                    renderedNode["script"] = {
                        "id": node.script.id,
                        "human_name": node.script.human_name,
                        "type": node.script.type,
                        "supported_file_types": node.script.supported_file_types,
                        "description": node.script.description
                    }
            else:
                if node.script is None:
                    renderedNode["script"] = None
                else:
                    script = node.script
                    serializer = PythonScriptSummarySerializer(script, many=False)
                    renderedNode["script"] = serializer.data

            renderedNodes[f"{node.id}"] = renderedNode

        for edge in edges:
            renderedEdges[f"{edge.id}"] = {
                "id": f"{edge.id}",
                "from": {
                    "nodeId": f"{edge.start_node.id}",
                    "portId": "output"
                },
                "to": {
                    "nodeId": f"{edge.end_node.id}",
                    "portId": "input"
                }
            }

        digraph['nodes'] = renderedNodes
        digraph['links'] = renderedEdges

        print("Digraph is: ")
        print(digraph)

        pipeline.digraph=digraph
        pipeline.save()

        return JOB_SUCCESS

    except Exception as e:
        returnMessage = "{0} - Error rendering digraph for pipeline ID #{1}: {2}".format(JOB_FAILED_DID_NOT_FINISH, pipelineId, e)
        return returnMessage

@celery_app.task(base=FaultTolerantTask, name="Run Job")
def runJob(*args, jobId=-1, endStep=-1, **kwargs):

    try:

        if jobId == -1:
            raise PipelineError(message="ERROR - No job ID was specified for runJobGremlin. You must specify a jobId.")

        if len(Job.objects.filter(id=jobId)) != 1:
            raise PipelineError(message="ERROR - There appears to be no job with jobId = {0}.".format(jobId))

        #Redirect stdout and setup a job logger which will collect stdout on finish and then write to DB
        temp_out = StringIO()
        jobLogger = JobLogger(jobId=jobId, name="runJob")

        job = Job.objects.get(id=jobId)

        job.start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        job.queued = False
        job.started = True
        job.status = "Running..."
        job.save()

        pipeline = job.pipeline
        temp_out.write("Job pipeline is: {0}".format(pipeline))
        temp_out.write("\nJob pipeline is: {0}".format(pipeline))

        # flatten the digraph and ensure every node only runs after all of the nodes on which it could depend run...
        # this is probably the *least* efficient way to handle this
        # essentially taking a digraph and reducing it to a sequence of steps that is linear.
        # you could see a better approach maybe being reducing it to "layers" and having a 2d array of layers
        # where each "layer" is an array of arrays of all of the same nodes on the same level of the same branch of
        # the digraph (if you think about is as a tree - which, duh, it's not, but hopefully that helps illustrate
        # the possible next iteration of this.
        root = pipeline.root_node
        temp_out.write(f"Root node: {root}")
        pipeline_nodes = buildNodePipelineRecursively(pipeline, node=root)
        temp_out.write("\nRaw pipeline nodes are: {0}".format(pipeline_nodes))

        jobDocs = Document.objects.filter(job=jobId)
        temp_out.write("\nJob has {0} docs.".format(len(jobDocs)))

        celery_jobs = []

        # Build the celery job pipeline (Note there may be some inefficiencies in how this is constructed)
        # Will fix in future release.
        logger.info("Build celery instructions")
        for node in pipeline_nodes:

            # Start with a job to ensure all of the documents are extracted
            # You can't just use a group here, however, as we want to chain further jobs to it and that will
            # create the group to a chord in a way we don't want. A workaround is to just treat this as a chord
            # from the start, which will then allow us to chain the chords and get desired behavior IF we use
            # a dummy chord terminator (as there's nothing we want to do with the underlying extractTextForDoc
            # return values.
            # See more here: https://stackoverflow.com/questions/15123772/celery-chaining-groups-and-subtasks-out-of-order-execution
            if node.type == "ROOT_NODE":
                logger.info("Build root node celery instructions")
                celery_jobs.append(createSharedResultForParallelExecution.si(jobId=jobId, stepId=node.id))
                celery_jobs.append(chord(
                    group([extractTextForDoc.s(docId=d.id) for d in jobDocs]),
                    resultsMerge.si(jobId=jobId, stepId=node.id)))

            # TODO - handle packaging step separately similar to the root_node above
            # For through jobs...
            elif node.type == "THROUGH_SCRIPT":
                if node.script.type == PythonScript.RUN_ON_JOB_ALL_DOCS_PARALLEL:
                    celery_jobs.append(createSharedResultForParallelExecution.si(jobId=jobId, stepId=node.id))
                    celery_jobs.append(chord(
                        group([applyPythonScriptToJobDoc.s(docId=d.id, jobId=jobId, nodeId=node.id,
                                                     scriptId=node.script.id)
                         for d in jobDocs]),
                        resultsMerge.si(jobId=jobId, stepId=node.id)))
                elif node.script.type == PythonScript.RUN_ON_JOB:
                    celery_jobs.append(
                        applyPythonScriptToJob.s(jobId=jobId, nodeId=node.id, scriptId=node.script.id))
                else:
                    raise PipelineError(message="{0} - {1}".format(JOB_FAILED_DID_NOT_FINISH,
                                                 "Unrecognized script type: {0}".format(node.script.type)))

        # add last step which will shut down the job when the tasks complete
        celery_jobs.append(packageJobResults.s(jobId=jobId))
        celery_jobs.append(stopPipeline.s(jobId=jobId))

        logger.info("Final pipeline jobs list:")
        logger.info(str(celery_jobs))

        logger.info("Starting task chain...")
        data = chain(celery_jobs).apply_async()

        logger.info("Finished task chain...")
        jobLogger.info(temp_out.getvalue())

        return data

    except Exception as e:

        returnMessage = "{0} - Error on Run Job #{1}: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId, e)
        stopJob(jobId=jobId, status=returnMessage, error=True)
        traceback.print_exc(file=temp_out)
        jobLogger.error(returnMessage)
        jobLogger.info(temp_out.getvalue())
        return returnMessage

# shutdown the job
@celery_app.task(base=FaultTolerantTask, name="Stop Current Pipeline")
def stopPipeline(*args, jobId=-1, **kwargs):

    temp_out = StringIO()
    sys.stdout = temp_out
    jobLogger = JobLogger(jobId=jobId, name="runJob")

    returnMessage = JOB_FAILED_DID_NOT_FINISH
    error=False

    temp_out.write(f"Trying to stop pipeline for job {jobId} with args of: {args}")

    if len(args) > 0 and not jobSucceeded(args[0]):
        returnMessage = "{0} - Pipeline failure for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId,
                                                                               args[0])
        stopJob(jobId=jobId, status=returnMessage, error=True)

    else:
        try:
            temp_out.write(f"\nStopped job Id{jobId}")
            returnMessage = JOB_SUCCESS
            error = False

        except Exception as err:
            returnMessage = "{0} - Error on stopping job #{1}: {2}".format(
                JOB_FAILED_DID_NOT_FINISH, jobId, err)
            traceback.print_exc(file=temp_out)
            jobLogger.error(returnMessage)
            error=True

    stopJob(jobId=jobId, status=JOB_SUCCESS, error=error)
    temp_out.write(returnMessage)
    sys.stdout = sys.__stdout__
    jobLogger.info(msg=temp_out.getvalue())
    return returnMessage


# this should only be run by the public tasks in this file. It has more limited error handling as it assumes this was handled successfully earlier.
# processingTask is assumed to take arguments job and doc
@celery_app.task(base=FaultTolerantTask, name="Celery Wrapper for Python Job Doc Task")
def applyPythonScriptToJobDoc(*args, docId=-1, jobId=-1, nodeId=-1, scriptId=-1, **kwargs):

    # Create local logging data object
    jobLog = StringIO()
    jobLogger = JobLogger(jobId=jobId, name="applyPythonScriptToJobDoc")

    jobLog.write("\napplyPythonScriptToJobDoc - args is:{0}".format(args))
    jobLog.write("\napplyPythonScriptToJobDoc - docId is:{0}".format(docId))
    jobLog.write("\napplyPythonScriptToJobDoc - jobId is:{0}".format(jobId))
    jobLog.write("\napplyPythonScriptToJobDoc - stepId is:{0}".format(nodeId))
    jobLog.write("\napplyPythonScriptToJobDoc - scriptId is:{0}".format(scriptId))

    if len(args) > 0:
        jobLog.write(f"\nPrevious job succeeded: {jobSucceeded(args[0])}")
        jobLog.write("\napplyPythonScriptToJobDoc - args are: {0}".format(args))

    try:

        # Get required objs
        job = Job.objects.get(id=jobId)

        if job.error:
            raise PrecedingNodeError(message="Job is already in error state. Irrecoverable.")

        if job.finished:
            raise JobAlreadyFinishedError(
                message="Job somehow is already marked as complete yet node is trying to start.")

        if len(args) > 0 and not jobSucceeded(args[0]):
            raise PrecedingNodeError(message="Previous node has already failed: {0}".format(args[0]))

        # Setup the result for this node / script
        result = Result.objects.create(
            name="Job: {0} | Pipeline Node #{1}".format(jobId, nodeId),
            job_id=jobId,
            pipeline_node_id=nodeId,
            doc_id=docId,
            type='DOC',
            start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            started=True,
            finished=False,
            error=False,
        )
        result.save()

        #If job checks out, get remaining objects
        doc = Document.objects.get(id=docId)
        pipeline_node = PipelineNode.objects.get(id=nodeId)
        script = pipeline_node.script

        # Check that the input files are compatible with scripts:
        supported_doc_types = json.loads(pipeline_node.script.supported_file_types)
        if not doc.type in supported_doc_types:
            raise FileNotSupportedError(message="{0} - Cannot run script {1} on doc type {2} as it"
                                                " is not in supported file types: {3}".format(
                JOB_FAILED_UNSUPPORTED_FILE_TYPE,
                scriptId,
                doc.type,
                supported_doc_types
            ))

        else:
            jobLog.write("\nDoc type {0} IS supported by script ID #{1}".format(
                doc.type,
                scriptId
            ))

        # If there was a preceding step, grab the data from that step and pass it as an input, otherwise, this is a
        # first (possibly only) step and we want to pass in job settings.
        try:
            preceding_data = getPrecedingResults(job, pipeline_node)
            jobLog.write(f"Successfully got preceding data: {preceding_data}")

        except Exception as e:
            jobLog.write(f"\nTrying to build preceding data but encountered an unexpected error: {e}")
            traceback.print_exc(file=jobLog)

        # transform the scriptInputs (if there is a transform script provided)
        transformed_data = preceding_data
        if pipeline_node.input_transform:
            transformed_data = transformStepInputs(pipeline_node.input_transform, preceding_data)

        # Build json inputs for job, which are built from both step settings in the job settings and
        # and the step_settings store. Dictonaries are combined. If key exists in both job and step settings
        # the job key will overwrite the step key's value.
        script_inputs = buildScriptInput(pipeline_node, job, script)

        # Store input data
        result.input_settings = script_inputs
        result.raw_input_data = preceding_data
        result.transformed_input_data = transformed_data
        result.save()

        # Try to load the document into byte object to be passed into user scripts
        # User scripts will NOT get any of the underlying django objs. This abstracts
        # away the underlying django / celery system and also makes it harder to do bad
        # things
        docBytes = None

        usingS3 = (
                settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")
        jobLog.write("UsingS3: {0}".format(usingS3))

        # if the rawText field is still empty... assume that extraction hasn't happened.
        # for some file types (like image-only pdfs), this will not always be right.
        if doc.file:

            # if we're using Boto S3, we need to interact with the files differently
            if usingS3:
                filename = doc.file.name
                jobLog.write(str(filename))

            else:
                jobLog.write("Not using S3")
                filename = doc.file.path

            # Load the file object from Django storage backend
            docBytes = default_storage.open(filename, mode='rb').read()

        # This is only going to capture log entries from within the user's scripts.
        scriptLogger = TaskLogger(resultId=result.id, name="User_Doc_Script")
        jobLog.write(f"\nStarting script for job ID #{job.id} (step # {pipeline_node.step_number} on "
                     f"doc ID #{doc.id}) with inputs: {script_inputs}")
        jobLog.write(f"Doc is {doc}")
        jobLog.write(f"Doc has text: {len(doc.rawText) > 0}")

        # Run the user script but wrap in a try / except so we don't crash the pipeline if this fails
        finished, message, data, fileBytes, file_ext = createFunctionFromString(script.script)(
            *args,
            docType=doc.type,
            docText=doc.rawText,
            docName=doc.name,
            docByteObj=docBytes,
            logger=scriptLogger,
            scriptInputs=script_inputs,
            previousData=transformed_data,
            **kwargs)

        jobLog.write(f"Finished {finished}")
        jobLog.write(f"Message {message}")
        jobLog.write(f"data {data}")
        jobLog.write(f"file extension {file_ext} of type {type(file_ext)}")

        # take file object and save to filesystem provided it is not none and plausibly could be an extension
        if file_ext and len(file_ext) > 1:
            name, file_extension = os.path.splitext(doc.name)
            file_data = ContentFile(fileBytes)
            result.file.save(
                "./step_results/{0}/{1}/{2}-{3}.{4}".format(jobId, nodeId, doc.id, name, file_ext),
                file_data)

        result.finished = True
        result.output_data = json.dumps(data)
        result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        result.save()

        if finished:

            # iterate job task completion count
            job.completed_tasks = job.completed_tasks + 1
            job.save()
            jobLog.write("Done")
            jobLogger.info(msg=jobLog.getvalue())
            return JOB_SUCCESS

        else:
            result.error = True
            result.save()

            raise UserScriptError(message="User script returned Finished=False. Node in error state.")


    except Exception as e:
        returnMessage = "{0} - Error in applyPythonScriptToJobDoc for job #{1}, script #{2}: {3}".format(
                JOB_FAILED_DID_NOT_FINISH,
                jobId,
                nodeId,
                e
        )
        jobLogger.error(msg=returnMessage)
        traceback.print_exc(file=jobLog)
        jobLog.write(returnMessage)
        jobLogger.info(message=jobLog.getvalue())
        stopJob(jobId=jobId, status=returnMessage, error=True)

        if result:
            result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            result.finished = True
            result.error = True
            result.save()

        return returnMessage

    return JOB_FAILED_DID_NOT_FINISH

@celery_app.task(base=FaultTolerantTask, name="Celery Wrapper for Python Job Task")
def applyPythonScriptToJob(*args, jobId=-1, nodeId=-1, scriptId=-1, **kwargs):

    nodeLog = StringIO() #Memory object to hold job logs for job-level commands (will redirect print statements)
    jobLogger = JobLogger(jobId=jobId, name="applyPythonScriptToJob")

    nodeLog.write("applyPythonScriptToJob - jobId: {0}".format(jobId))
    nodeLog.write("\napplyPythonScriptToJob - scriptId: {0}".format(scriptId))

    if len(args) > 0:
        nodeLog.write("\napplyPythonScriptToJobDoc - args are: {0}".format(args))
        nodeLog.write(f"\nPrevious job succeeded: {jobSucceeded(args[0])}")

    nodeLog.write("\napplyPythonScriptToJob - kwargs are: {0}".format(kwargs))

    try:

        # Check to see if parent job has gone into error state or, though this shouldn't happen, finished
        job = Job.objects.get(id=jobId)

        if job.error:
            raise PrecedingNodeError(message="Job is already in error state. Irrecoverable.")

        if job.finished:
            raise JobAlreadyFinishedError(
                message="Job somehow is already marked as complete yet node is trying to start.")

        if len(args) > 0 and not jobSucceeded(args[0]):
            raise PrecedingNodeError(message="Previous node has already failed: {0}".format(args[0]))

        result = Result.objects.create(
            name="Pipeline: {0} | Step #{1}".format(job.pipeline.id, nodeId),
            job=job,
            pipeline_node_id=nodeId,
            type='STEP',
            start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            started=True,
            finished=False,
            error=False,
        )
        result.save()

        pipeline_node = PipelineNode.objects.get(id=nodeId)
        script = pipeline_node.script

        # Build json inputs for job, which are built from both step settings in the job settings and
        # and the step_settings store.
        script_inputs = buildScriptInput(pipeline_node, job, script)

        # If there was a preceding step, grab the data from that step and pass it as an input, otherwise, this is a
        # first (possibly only) step and we want to pass in job settings.
        # If there was a preceding step, grab the data from that step and pass it as an input, otherwise, this is a
        # first (possibly only) step and we want to pass in job settings.
        preceding_data = {}
        try:
            preceding_data = getPrecedingResults(job, pipeline_node)
            nodeLog.write(f"Successfully got preceding data: {preceding_data}")

        except Exception as e:
            nodeLog.write(f"\nTrying to build preceding data but encountered an unexpected error: {e}")
            traceback.print_exc(file=nodeLog)

        nodeLog.write("\nStarting data transform")

        # transform the scriptInputs (if there is a transform script provided)
        transformed_data = preceding_data

        if pipeline_node.input_transform:
            transformed_data = transformStepInputs(pipeline_node.input_transform, preceding_data)

        nodeLog.write("\nData transform complete")

        result.input_settings=json.dumps(script_inputs)
        result.raw_input_data=json.dumps(preceding_data)
        result.transformed_input_data=json.dumps(transformed_data)
        result.save()

        # This will only get logs from within user's script if they actually use the logger.
        scriptLogger = TaskLogger(resultId=result.id, name="User_Job_Script")
        nodeLog.write(f"\nStarting script for job ID #{job.id} (step # {pipeline_node.step_number}) "
                    f"with inputs: {script_inputs}")

        # call the script with the appropriate Gremlin / Django objects already loaded (don't want the user
        # interacting with underlying Django infrastructure.
        finished, message, data, fileBytes, file_ext, docPackaging = createFunctionFromString(script.script)(*args,
                                                                                                             job=job,
                                                                                                             step=pipeline_node,
                                                                                                             logger=scriptLogger,
                                                                                                             scriptInputs=script_inputs,
                                                                                                             previousData=transformed_data,
                                                                                                             **kwargs)

        nodeLog.write(f"Script finished: {finished}")
        nodeLog.write(f"Message: {message}")
        nodeLog.write(f"Data: {data}")
        nodeLog.write(f"File extension {file_ext} of type {type(file_ext)}")
        nodeLog.write(f"Doc packaging instructions are {docPackaging}")

        # if there is a set of doc packaging instructions, build the doc package
        if docPackaging and isinstance(docPackaging, dict):

            packageBytes = io.BytesIO()
            packageZip = ZipFile(packageBytes, mode='w', compression=zipfile.ZIP_DEFLATED)

            # if we're using Boto S3 adapter to store docs in AWS, we need to interact with the files differently
            usingS3 = (settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")

            for returnDocId in list(docPackaging.keys()):

                doc = Document.objects.get(id=returnDocId)

                if usingS3:
                    filename = doc.file.name

                # If they're in the local file system
                else:
                    filename = doc.file.path

                docPath = Path(filename)

                with default_storage.open(filename, mode='rb') as file:
                    nodeLog.write(f"newChildPath root is {Path(docPackaging[returnDocId])}")
                    newChildPath = f"{docPackaging[returnDocId]}/{docPath.name}"
                    nodeLog.write(f"newChildPath is {newChildPath}")
                    packageZip.writestr(newChildPath, file.read())

            packageZip.close()

            result.file.save("./step_results/{0}/{1}/Step {2} ({3}).{4}".format(
                jobId,
                nodeId,
                pipeline_node.name,
                pipeline_node.step_number + 1,
                "zip"),
                ContentFile(packageBytes.getvalue())
            )

        # Otherwise, store the file object returned
        # take file object and save to filesystem provided it is not none and plausibly could be an extension
        elif file_ext and len(file_ext) > 1:
            file_data = ContentFile(fileBytes)
            result.file.save("./step_results/{0}/{1}/Step {2} ({3}).{4}".format(
                    jobId,
                    nodeId,
                    pipeline_node.name,
                    pipeline_node.step_number + 1,
                    file_ext
                ),
                file_data
            )

        result.output_data = json.dumps(data, indent=4)
        result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        result.finished=True
        result.save()

        if finished:

            # iterate job task completion count
            job.completed_tasks = job.completed_tasks + 1
            job.save()
            nodeLog.write("Done")
            jobLogger.info(msg=nodeLog.getvalue())
            return JOB_SUCCESS

        else:
            result.error=True
            result.save()
            raise UserScriptError(message="User script returned Finished=False. Node in error state.")

    except Exception as e:
        returnMessage = "{0} - Error on Step #{1} for Job {2}: {3}".format(
            JOB_FAILED_DID_NOT_FINISH,
            nodeId,
            jobId,
            e
        )
        jobLogger.error(returnMessage)
        traceback.print_exc(file=nodeLog)
        jobLogger.info(nodeLog.getvalue())
        stopJob(jobId=jobId, status=returnMessage, error=True)

        if result:
            result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            result.error = True
            result.finished = True
            result.save()

        return returnMessage

    return JOB_FAILED_DID_NOT_FINISH

# Apparently, celery will NOT let you chain two groups without automatically converting the groups to chords.
# This is not really desired and is killing my workflow... the workaround is to terminate each group in chain with this "chordfinisher"
# to nullify celery's conversion into chord and then you get behavior you want from chaining the groups.
# read more here:
# https://stackoverflow.com/questions/15123772/celery-chaining-groups-and-subtasks-out-of-order-execution
@celery_app.task(base=FaultTolerantTask)
def chordfinisher(previousMessage, *args, **kwargs):

    return previousMessage

# Tee up a parallel step by creating step result with proper start time... otherwise we'll lose
@celery_app.task(base=FaultTolerantTask)
def createSharedResultForParallelExecution(*args, jobId=-1, stepId=-1, **kwargs):

    logger.info("createSharedResultForParallelExecution - jobId {0} and stepId {1}".format(jobId, stepId))

    try:

        logger.info("Creating result...")

        job = Job.objects.get(id=jobId)
        logger.info("Job object {0}".format(job))
        step = PipelineNode.objects.get(id=stepId)
        logger.info("Step object: {0}".format(step))

        logger.info("Create step_result")

        # Currently the root node script is null and root nodes just trigger a built-in celery job...
        # I need to update the system so it creates a default root node type *object* in the DB and treats
        # root nodes more like other node types... eventually.
        if step.type == PipelineNode.ROOT_NODE:
            name = "Pipeline: {0} | Step #{1}".format(job.pipeline.name, "BUILT-IN"),
        else:
            name = "Pipeline: {0} | Step #{1}".format(job.pipeline.name, step.script.name),

        step_result = Result.objects.create(
            name=name,
            job=job,
            pipeline_node=step,
            type='STEP',
            start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            stop_time=None,
            started=True,
            finished=False,
            error=False
        )
        step_result.save()

        logger.info("Created result for parallel execution step: ")
        print(step_result)

        return JOB_SUCCESS

    except Exception as e:
        return "{0} - Error trying to start parallel step. Perhaps specified job or pipeline is wrong? This shouldn't " \
               "ever happen (comforting, right?). Exception is: {1}".format(JOB_FAILED_DID_NOT_FINISH, e)

# Package up all of the individual results data objs for a given step
# and pass them along to the next step
@celery_app.task(base=FaultTolerantTask)
def resultsMerge(*args, jobId=-1, stepId=-1, **kwargs):

    logger.info("Results merge for stepId {0} of jobId {1}".format(stepId, jobId))

    # Get loggers
    jobLogger = JobLogger(jobId=jobId, name="resultsMerge")
    mergeLog = StringIO() #Memory object to hold job logs for job-level commands (will redirect print statements)

    # Setup control variables
    error = False

    # Default return message code
    returnMessage = JOB_FAILED_DID_NOT_FINISH

    logger.info("######### Results Merge At End of Parallel Step:")

    for arg in args:
        mergeLog.write(arg)

    job = Job.objects.get(id=jobId)
    step = PipelineNode.objects.get(id=stepId)
    results = Result.objects.filter(pipeline_node=step, job=job)

    # For parallel steps, the step result should have been created before the execution split in parallel workers, so
    # fetch that earlier result to preserve original start time and store results of the parallel execution
    logger.info("Try to fetch parallel step result created earlier:")
    step_result = Result.objects.get(pipeline_node=step, job=job, type=Result.STEP)
    logger.info("Step result retrieved from memory is: ")
    logger.info(step_result)

    logger.info("Start results merger for {0} results.".format(str(len(results))))

    input_settings = {}
    transformed_inputs = {}
    raw_inputs = {}
    outputs = {}

    for result in results:

        logger.info(f"\nTry to package result for {result.name}")

        try:
            input_settings[f"{result.id}"] = json.loads(result.input_settings)
        except Exception as e:
            logger.info(f"\nError while trying to input settings for step {result.pipeline_node.step_number} and " \
                   f"doc {result.id}: {e}")
            input_settings[f"{result.id}"] = {}
            error = True

        try:
            transformed_inputs[f"{result.id}"] = json.loads(result.transformed_input_data)

        except Exception as e:

            mergeLog(f"\nError while trying to merge transformed input data for step {result.pipeline_node.step_number} "
                     f"and doc {result.id}: {e}")
            transformed_inputs[f"{result.id}"] = {}
            error = True

        try:
            raw_inputs[f"{result.id}"] = json.loads(result.input_data.raw_input_data)

        except Exception as e:
            mergeLog.write(f"\nWARNING - Error while trying to merge raw input data for step {result.pipeline_node.step_number} and " \
                   f"doc {result.id}: {e}")
            raw_inputs[f"{result.id}"] = {}

        try:
            outputs[f"{result.id}"] = json.loads(result.output_data.output_data)
        except Exception as e:
            mergeLog.write(f"WARNING - Error while trying to merge output data for step {result.pipeline_node.step_number} and " \
                   f"doc {result.id}: {e}")
            outputs[f"{result.id}"] = {}
            error = True

    mergeLog.write("\Step result created and saved.")

    # iterate job step completion count
    job.completed_tasks = job.completed_tasks + 1
    job.save()

    step_result.stop_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    step_result.raw_input_data=json.dumps(raw_inputs)
    step_result.transformed_input_data=json.dumps(transformed_inputs)
    step_result.output_data=json.dumps({"documents": outputs})
    step_result.finished = True
    step_result.terror = error
    step_result.save()

    mergeLog.write("\nResults merger complete.")

    jobLogger.info(msg=mergeLog.getvalue())

    return JOB_SUCCESS


@celery_app.task(base=FaultTolerantTask, name="Ensure Script is Available")
def prepareScript(*args, jobId=-1, scriptId=-1, **kwargs):
    try:
        if len(args) > 0 and not jobSucceeded(args[0]):
            message = "{0} - Preceding task failed for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH,
                                                                                        jobId,
                                                                                        args[0])
            stopJob(jobId=jobId, status=message, error=True)
            return message

        script = PythonScript.objects.get(id=scriptId)
        packages = script.required_packages.split("\n")

        if len(packages) > 0:
            logging.info(f"Script requires {len(packages)} packages. "
                         f"Ensure required packages are installed:\n {script.required_packages}")

            p = subprocess.Popen([sys.executable, "-m", "pip", "install", *packages], stdout=subprocess.PIPE)
            out, err = p.communicate()

            # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
            out = codecs.getdecoder("unicode_escape")(out)[0]
            if err:
                err = codecs.getdecoder("unicode_escape")(err)[0]
                logging.error(f"Errors from script pre check: \n{err}")

            logging.info(f"Results of script pre check: \n{out}")

        setupScript = script.setup_script
        if setupScript != "":

            lines = setupScript.split("\n")

            for line in lines:

                p = subprocess.Popen(line.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = p.communicate()

                # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
                out = codecs.getdecoder("unicode_escape")(out)[0]
                if err:
                    err = codecs.getdecoder("unicode_escape")(err)[0]
                    logging.error(f"Errors from script pre check: \n{err}")

                logging.info(f"Results of script pre check: \n{out}")

        envVariables = script.env_variables
        if envVariables != "":
            logging.info(f"It appears there are env variables: {envVariables}")

            vars = {}
            try:
                vars = json.loads(envVariables)
                logging.info(f"Parsed following env var structure: {vars}")
            except:
                logging.warning("Unable to parse env variables.")
                pass

            for e, v in vars.items():
                logging.info(f"Adding env_var {e} with value {v}")
                os.environ[e] = v

        return JOB_SUCCESS

    except Exception as e:
        message = "{0} - Error trying to ensure script is setup: {1}".format(
            JOB_FAILED_INVALID_DOC_ID, e)
        logger.error(message)
        return message


# Task to install a python package list (same as you would a la "pip install package1 package 2 package3 package...")
@celery_app.task(base=FaultTolerantTask, name="Install Python Package")
def installPackages(*args, scriptId=-1, **kwargs):
    log = "#################### Package Install Log ####################\n\n{1}"

    # call pip as subprocess in current environment. Capture output using p.communicate()
    # based on: https://stackoverflow.com/questions/2502833/store-output-of-subprocess-popen-call-in-a-string
    for package in args:
        p = subprocess.Popen([sys.executable, "-m", "pip", "install", package], stdout=subprocess.PIPE)
        out, err = p.communicate()

        # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
        out = codecs.getdecoder("unicode_escape")(out)[0]
        log = log + "\n\n" + out

    script = PythonScript.objects.get(id=scriptId)
    script.setup_log = log
    script.save()

    return "{0} - Package install: {1}".format(JOB_SUCCESS, out)


# Task to run arbitrary python code from a string. This is a grave security risk if ever exposed outside very limited #s
# of admins. Be careful how this is exposed to users. It seems necessary for installing new packages, but, long-term,
# there needs to be a way to install new scripts, install packages and run any necessary setup steps
@celery_app.task(base=FaultTolerantTask, name="Run Python Setup Script From Text")
def runPythonScriptSetup(*args, scriptId=-1, **kwargs):

    returnMessage = JOB_FAILED_DID_NOT_FINISH

    temp_out = StringIO()
    sys.stdout = temp_out

    print("#################### Setup Script Log ####################\n\n")

    try:
        # call pip as subprocess in current environment. Capture output using p.communicate()
        # based on: https://stackoverflow.com/questions/2502833/store-output-of-subprocess-popen-call-in-a-string
        print("Script setup arguments are: ")
        print(args)

        for line in args:
            print(line.split())
            p = subprocess.Popen(line.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()

            # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
            out = codecs.getdecoder("unicode_escape")(out)[0]
            err = codecs.getdecoder("unicode_escape")(err)[0]

            print("\nSuccess:\n" + out + "\nErrors:\n" + err)

        script = PythonScript.objects.get(id=scriptId)
        script.setup_log = script.setup_log + "\n\n" + temp_out.getvalue()
        script.save()

        returnMessage = "{0} - Package install: {1}".format(JOB_SUCCESS, out)

    except Exception as e:
        print(f"Error with install: {e}")

    sys.stdout = sys.__stdout__
    return returnMessage

# create a new package for a python script... can be imported dynamically later
@celery_app.task(base=FaultTolerantTask, name="Create New Package")
def createNewPythonPackage(*args, scriptId=-1, **kwargs):
    script = PythonScript.objects.get(id=scriptId)
    newModuleDirectory = "./Jobs/tasks/scripts/{0}".format(script.name)

    # Create directories for cluster results if it doesn't exist
    if not os.path.exists(newModuleDirectory):
        os.makedirs(newModuleDirectory)

    pythonFileName = "{0}/{1}.py".format(newModuleDirectory, script.name)

    with open(pythonFileName, "w+") as file1:
        file1.write(script.script)

    with open(newModuleDirectory + "/__init__.py", "w+") as file1:
        file1.write("#Created by Gremlin")


@celery_app.task(base=FaultTolerantTask, name="Extract Document Text")
def extractTextForDoc(docId=-1):
    logging.info(f"Try to extract doc for docId={docId}")

    if docId == -1:
        message = "{0} - No doc ID was specified for extractTextForDoc. You must specify a docId.".format(
            JOB_FAILED_INVALID_DOC_ID)
        logger.error(message)
        return message

    else:
        try:

            logger.info("Attempting to retrieve doc")
            # I believe the issue here is the task fires before the file is saved due to increased latency
            # of S3 and my network
            # See here: https://stackoverflow.com/questions/11539152/django-matching-query-does-not-exist-after-object-save-in-celery-task

            d = Document.objects.get(id=docId)
            logger.info(f"Doc model retrieved: {d}")
            usingS3 = (settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")
            logger.info("UsingS3: {0}".format(usingS3))

            # if the rawText field is still empty... assume that extraction hasn't happened.
            # for some file types (like image-only pdfs), this will not always be right.
            if not d.rawText:

                logger.info("No rawText detected... attempt to extract")

                # if we're using Boto S3, we need to interact with the files differently
                if usingS3:

                    logger.info("Using S3")
                    filename = d.file.name

                else:

                    logger.info("Not using S3")
                    filename = d.file.path

                logger.info(str(filename))
                name, file_extension = os.path.splitext(filename)
                logger.info("file_extension is: {0}".format(file_extension))

                # Load the file object from Django storage backend
                file_object = default_storage.open(filename, mode='rb')
                logger.info("file_object loaded")

                if file_extension == ".docx":

                    logger.info("Appending: " + filename)
                    rawText = docx2txt.process(file_object)
                    d.rawText = rawText
                    d.extracted = True
                    d.save()

                    logger.info("Successfully extracted txt from .docX: " + filename)

                elif file_extension == ".doc" or file_extension == ".pdf" or file_extension == ".pdfa":
                    logger.info(f"Appending AND CONVERTING {file_extension}: " + filename)

                    # Tika source code comments suggest it can open a binary file... but actual code trace...
                    # suggests that it cannot. I could be wrong, but it keeps choking on binary file and I'm
                    # tired of screwing with it. Write a temp file with nearly impossible likelihood of collission.
                    # pass filename to tika. Will delete on finish.

                    # save current word doc to temp file
                    # nice overview of file modes: https://stackoverflow.com/questions/16208206/confused-by-python-file-mode-w
                    # file copy code from https://stackoverflow.com/questions/36875258/copying-one-files-contents-to-another-in-python
                    try:
                        with tempfile.NamedTemporaryFile(prefix='gremlin_', suffix=file_extension, delete=True) as tf:

                            copyfileobj(file_object, tf)
                            parsed = parser.from_file(tf.name)
                            rawText = parsed["content"]
                            d.rawText = rawText
                            d.extracted = True
                            d.save()

                    except Exception as e:
                        logger.warning(f"Error encountered while trying to parse document: {e}")

                    logger.info("Successfully extracted txt from .doc: " + filename)

                    return JOB_SUCCESS

                else:
                    message = "{0} - Gremlin currently doesn't support file {0} with extension of {0}".format(
                        JOB_FAILED_DID_NOT_FINISH, filename, file_extension)
                    logger.error(message)
                    return message

                file_object.close()

            else:
                return JOB_SUCCESS
        except Exception as e:
            message = "{0} - Error extracting doc #{1}. Error: {2}".format(JOB_FAILED_DID_NOT_FINISH, d.id, e)
            logger.error(message)
            return message


@celery_app.task(base=FaultTolerantTask, name="Package Job Result")
def packageJobResults(*args, jobId=-1, **kwargs):

    jobLogger = logging.LoggerAdapter(job_logger, extra={"jobId": jobId})
    jobLogger.info(f"Package Job Results for Job ID {jobId}")

    if len(args) > 0 and not jobSucceeded(args[0]):
        message = "{0} - Preceding task failed for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId,
                                                                                    args[0])
        stopJob(jobId=jobId, status=message, error=True)
        return message

    try:

        # TODO - also need to update how final results are aggregated to include step results.
        jobLogger.info("Try to package results for job #{0}".format(jobId))

        allResults = Result.objects.filter(job=jobId)
        stepResults = Result.objects.filter(job=jobId, type="STEP")

        job = Job.objects.get(id=jobId)
        logger.info(
            "Job #{0} has {1} step results and {2} results total.".format(jobId, len(stepResults), len(allResults)))

        usingS3 = (settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")
        jobLogger.info("UsingS3: {0}".format(usingS3))

        resultsDir = "./jobs_data/%s/" % (jobId)
        resultFilename = "%sJob %s - Results.zip" % (resultsDir, jobId)

        zipBytes = io.BytesIO()
        jobData = {}

        with ZipFile(zipBytes, mode="w", compression=zipfile.ZIP_DEFLATED) as jobResultsZipData:

            for num, r in enumerate(allResults):

                jobLogger.info("Try packaging file result ({0}) into job # {1}".format(r.id, jobId))

                if r.file:

                    jobLogger.info("There is a file object associated with this result.")

                    # if we're using Boto S3 adapter to store docs in AWS, we need to interact with the files differently
                    if usingS3:
                        filename = r.file.name

                    # If they're in the local file system
                    else:
                        filename = r.file.path

                    jobLogger.info("Result {0} has file ({1})".format(r.id, filename))

                    zip_filename = os.path.basename(filename)
                    jobLogger.info("zip_filename")
                    jobLogger.info(zip_filename)

                    with default_storage.open(filename, mode='rb') as file:
                        newChildPath = "./Step {0} ({1})/{2}".format(r.pipeline_node.step_number + 1,
                                                                     r.pipeline_node.name, zip_filename)
                        jobLogger.info(f"Zip file will be: {newChildPath}")
                        jobResultsZipData.writestr(newChildPath, file.read())
                        jobLogger.info("	--> DONE")

                else:
                    jobLogger.info("There is not file object associated with this result.")

        jobResultsZipData.close()

        # Step results already aggregated doc results, so we don't want to include those when assembling data.
        for num, r in enumerate(stepResults):
            # aggregate the result data from each results object under the job object.
            if r.output_data:
                jobLogger.info("Job has results data. Not logging as we don't know how large it is...")
                try:
                    stepData = json.loads(r.output_data)
                    jobData = {**jobData, **{r.pipeline_node.step_number: stepData}}
                    jobLogger.info("Appears we added this result successfully")
                except Exception as e:
                    jobLogger.warning("There was an error trying to append data: {0}".format(e))
            else:
                jobLogger.info("There is no result data")

        # Use Django to write Bytes data to result file for job from memory

        zipFile = ContentFile(zipBytes.getvalue())

        # Save the resulting job data. TODO - THIS SEEMS WRONG HOW THIS IS HANDLED.
        jobLogger.info("Stringify job outputs for saving.")
        jobLogger.info("Job outputs saved.")

        result = Result.objects.create(
            name="Job {0}".format(jobId),
            job=job,
            type='JOB',
            output_data=json.dumps(jobData)
        )
        result.file.save(resultFilename, zipFile)
        result.save()

        job.file.save(resultFilename, zipFile)
        # iterate job step completion count to include the package step (which can take a while so must
        # be included lest user feel job is "hanging" as task steps are completed 100% only to wait
        # for the package job.
        job.completed_tasks = job.completed_tasks + 1
        job.save()

        return JOB_SUCCESS

    except Exception as e:
        message = "Error saving job {0}: {1}".format(jobId, e)
        jobLogger.error(message)
        return "{0} - {1}".format(JOB_FAILED_DID_NOT_FINISH, message)
