from __future__ import absolute_import, unicode_literals

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
from ..models import Job, Document, PipelineStep, Result, PythonScript, ResultInputData, ResultData
from celery import chain, group, chord
from celery.signals import celeryd_after_setup
from .task_helpers import exec_with_return, returnScriptMethod, buildScriptInput, \
    transformStepInputs, createFunctionFromString
from .taskLoggers import JobLogger, TaskLogger
from shutil import copyfileobj, rmtree
from django.conf import settings
from datetime import datetime
import subprocess
import sys
import celery
import codecs
import os
import io
import docx2txt
import uuid
import json
import time
import jsonschema

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
        scripts=PythonScript.objects.all()

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


@celery_app.task(base=FaultTolerantTask, name="Run Script Installs")
def runScriptInstalls(*args, scriptId=-1, **kwargs):

    try:
        pythonScript=PythonScript.objects.get(id=scriptId)

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
        logging.error(f"Error setting running python script installers.\nScript ID:{scriptId}.\n"
                      f"Error: \n{e}")


@celery_app.task(base=FaultTolerantTask, name="Run Job")
def runJob(*args, jobId=-1, endStep=-1, **kwargs):
    if jobId == -1:
        logger.error("No job ID was specified for runJobGremlin. You must specify a jobId.")
        return JOB_FAILED_INVALID_JOB_ID

    elif len(Job.objects.filter(id=jobId)) != 1:
        logger.error("There appears to be no job with jobId = {0}.".format(jobId))
        return JOB_FAILED_INVALID_DOC_ID

    else:

        log = ""
        jobLogger = JobLogger(jobId=jobId, name="runJob")

        try:

            job = Job.objects.get(id=jobId)

            job.queued = False
            job.started = True
            job.status = "Running..."
            job.save()

            pipeline = job.pipeline
            log += "\nJob pipeline is: {0}".format(pipeline)

            # Get pipeline steps
            steps = PipelineStep.objects.filter(parent_pipeline=pipeline.id).all()
            log += "\nRaw pipeline steps are: {0}".format(steps)

            # Order the pipeline steps
            numbered_steps = {}
            for s in steps:
                numbered_steps[s.step_number] = s

            # Convert back to list
            pipeline_steps = []
            for i in range(0, len(steps)):
                pipeline_steps.append(numbered_steps[i])

            # If we specified an endStep (and it's <= the last step), truncate the pipeline_steps list.
            # This is useful to step through the pipeline steps to, for example,
            if endStep > -1 and endStep < len(pipeline_steps):
                pipeline_steps = pipeline_steps[0:endStep + 1]

            log += "\nTruncated job pipeline due to endStep flag has {0} steps: {1}".format(len(pipeline_steps),
                                                                                            pipeline_steps)

            jobDocs = Document.objects.filter(job=jobId)
            log += "\nJob has {0} docs.".format(len(jobDocs))

            celery_jobs=[]

            # Start with a job to ensure all of the documents are extracted
            # You can't just use a group here, however, as we want to chain further jobs to it and that will
            # create the group to a chord in a way we don't want. A workaround is to just treat this as a chord
            # from the start, which will then allow us to chain the chords and get desired behavior IF we use
            # a dummy chord terminator (as there's nothing we want to do with the underlying extractTextForDoc
            # return values.
            # See more here: https://stackoverflow.com/questions/15123772/celery-chaining-groups-and-subtasks-out-of-order-execution
            celery_jobs.append(chord(group(
                [extractTextForDoc.s(docId=d.id) for d in jobDocs]),
                chordfinisher.s()))

            # Build the celery job pipeline (Note there may be some inefficiencies in how this is constructed)
            # Will fix in future release.
            for step in pipeline_steps:
                # celery_jobs.append(prepareScript.s(jobId=jobId, scriptId=step.script.id))
                if step.script.type == PythonScript.RUN_ON_JOB_ALL_DOCS_PARALLEL:
                    celery_jobs.append(chord(group(
                        [applyPythonScriptToJobDoc.s(docId=d.id, jobId=jobId, stepId=step.id, scriptId=step.script.id)
                         for d in jobDocs]),
                        resultsMerge.si(jobId=jobId, stepId=step.id)))  # used to terminate with chordfinisher.s()
                elif step.script.type == PythonScript.RUN_ON_JOB:
                    celery_jobs.append(applyPythonScriptToJob.s(jobId=jobId, stepId=step.id, scriptId=step.script.id))
                else:
                    message = "{0} - {1}".format(JOB_FAILED_DID_NOT_FINISH,
                                                 "Unrecognized script type: {0}".format(step.script.type))
                    log += "\n" + message
                    return message

            # add last step which will shut down the job when the tasks complete
            celery_jobs.append(packageJobResults.s(jobId=jobId))
            celery_jobs.append(stopPipeline.s(jobId=jobId))

            log += "\nFinal pipeline jobs list:"
            log += "\n" + str(celery_jobs)
            log += "\nStarting task chain..."

            data = chain(celery_jobs).apply_async()

            log += "\nFinished task chain..."
            jobLogger.info(msg=log)

            return data

        except Exception as e:
            message = "Error on Run Job #{0}: {1}".format(jobId, e)
            log += "\n" + message
            stopJob(jobId=jobId, status=message, error=True)
            jobLogger.error(msg=log)
            return "{0} - {1}".format(JOB_FAILED_DID_NOT_FINISH, message)


# shutdown the job
@celery_app.task(base=FaultTolerantTask, name="Stop Current Pipeline")
def stopPipeline(*args, jobId=-1, **kwargs):
    jobLogger = JobLogger(jobId=jobId, name="runJob")
    log = f"Trying to stop pipeline for job {jobId} with args of: {args}"

    if len(args) > 0 and not jobSucceeded(args[0]):
        message = "{0} - Pipeline failure for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId,
                                                                               args[0])
        log += "\n" + message
        jobLogger.error(msg=log)
        stopJob(jobId=jobId, status=message, error=True)
        return message

    try:
        stopJob(jobId=jobId, status=JOB_SUCCESS, error=False)
        log += f"\nStopped job Id{jobId}"
        jobLogger.info(msg=log)
        return JOB_SUCCESS

    except Exception as err:
        message = "{0} - Error on stopping job #{1}: {2}".format(
            JOB_FAILED_DID_NOT_FINISH, jobId, err)
        log += "\n" + message
        jobLogger.error(msg=log)
        stopJob(jobId=jobId, status=message, error=True)
        return message


# this should only be run by the public tasks in this file. It has more limited error handling as it assumes this was handled successfully earlier.
# processingTask is assumed to take arguments job and doc
@celery_app.task(base=FaultTolerantTask, name="Celery Wrapper for Python Job Doc Task")
def applyPythonScriptToJobDoc(*args, docId=-1, jobId=-1, stepId=-1, scriptId=-1, **kwargs):

    log = "\napplyPythonScriptToJobDoc - args is:{0}".format(args)
    jobLogger = JobLogger(jobId=jobId, name="applyPythonScriptToJobDoc")

    if len(args) > 0:
        log += f"\nPrevious job succeeded: {jobSucceeded(args[0])}"
        log += "\napplyPythonScriptToJobDoc - args are: {0}".format(args)

    log += "\napplyPythonScriptToJobDoc - docId is:{0}".format(docId)
    log += "\napplyPythonScriptToJobDoc - jobId is:{0}".format(jobId)
    log += "\napplyPythonScriptToJobDoc - stepId is:{0}".format(stepId)
    log += "\napplyPythonScriptToJobDoc - scriptId is:{0}".format(scriptId)

    if len(args) > 0 and not jobSucceeded(args[0]):
        message = "{0} - Preceding task failed for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId,
                                                                                    args[0])
        log += "\n" + message
        jobLogger.error(msg=log)
        stopJob(jobId=jobId, status=message, error=True)
        return message

    try:
        doc = Document.objects.get(id=docId)
        job = Job.objects.get(id=jobId)
        step = PipelineStep.objects.get(id=stepId)
        script = PythonScript.objects.get(id=scriptId)

        # Check that the provided doc file type is compatible with the given script
        try:
            supported_doc_types = json.loads(step.script.supported_file_types)
            if not doc.type in supported_doc_types:
                message = "{0} - Cannot run script {1} on doc type {2} as it is not in supported file types: {3}".format(
                    JOB_FAILED_UNSUPPORTED_FILE_TYPE,
                    scriptId,
                    doc.type,
                    supported_doc_types
                )
                log += "\n" + message
                jobLogger.error(msg=log)
                return message
            else:
                log += "\nDoc type {0} IS supported by script ID #{1}".format(
                    doc.type,
                    scriptId
                )

        except:
            message = "{0} - Error parsing supported doc types for script #{1}".format(
                JOB_FAILED_DID_NOT_FINISH,
                stepId)
            log += "\n" + message
            jobLogger.error(msg=log)
            return message

        # Build json inputs for job, which are built from both step settings in the job settings and
        # and the step_settings store. Dictonaries are combined. If key exists in both job and step settings
        # the job key will overwrite the step key's value.
        scriptInputs = buildScriptInput(step.step_number,
                                        job.job_inputs,
                                        step.step_settings,
                                        step.script.required_inputs)

        # Try to load the document into byte object to be passed into user scripts
        # User scripts will NOT get any of the underlying django objs. This abstracts
        # away the underlying django / celery system and also makes it harder to do bad
        # things
        try:

            usingS3 = (settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")
            logger.info("UsingS3: {0}".format(usingS3))

            # if the rawText field is still empty... assume that extraction hasn't happened.
            # for some file types (like image-only pdfs), this will not always be right.
            if doc.file:

                # if we're using Boto S3, we need to interact with the files differently
                if usingS3:
                    filename = doc.file.name
                    logger.info(str(filename))

                else:
                    logger.info("Not using S3")
                    filename = doc.file.path

                # Load the file object from Django storage backend
                docBytes = default_storage.open(filename, mode='rb').read()

        except:
            docBytes = None


        # If there was a preceding step, grab the data from that step and pass it as an input, otherwise, this is a
        # first (possibly only) step and we want to pass in job settings.
        preceding_data = {}
        try:
            preceding = Result.objects.filter(job=job, job_step__step_number=step.step_number - 1, type="STEP")
            log += "\nPreceding step results jobs are: "
            log += "\n" + str(preceding)

            if len(preceding) == 1:
                try:
                    preceding = preceding[0].output_data.output_data
                    preceding_data = json.loads(preceding)
                except Exception as e:
                    log += f"\nFound preceding data and trying to load from json but encountered an error: {e}"
                    jobLogger.error(msg=log)
            else:
                log += f"\nIf there is preceding step data, the length of preceding step query set should be 1. It's {len(preceding)}"


        except Exception as e:
            log += f"\nTrying to build preceding data but encountered an unexpected error: {e}"

        # transform the scriptInputs (if there is a transform script provided)
        transformed_data = preceding_data
        if step.input_transform:
            transformed_data = transformStepInputs(step.input_transform, preceding_data)

        result = Result.objects.create(
            name="Pipeline: {0} | Step #{1}".format(job.pipeline.name, step.script.name),
            job=job,
            job_step=step,
            doc=doc,
            type='DOC',
            start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            input_settings=json.dumps(scriptInputs)
        )
        result.save()

        # Create object to hold our inputs (this helps with performance). They can get HUGE.
        # Storing them in the main result object really screws with performance.
        inputObj = ResultInputData.objects.create(
            raw_input_data=json.dumps(preceding_data),
            transformed_input_data=json.dumps(transformed_data),
        )
        inputObj.save()

        # Now link input data obj to the result
        result.input_data = inputObj
        result.save()

        # This is only going to capture log entries from within the user's scripts.
        scriptLogger = TaskLogger(resultId=result.id, name="User_Doc_Script")
        log += f"\nStarting script for job ID #{job.id} (step # {step.step_number} on doc ID #{doc.id}) with inputs: {scriptInputs}"

        try:
            finished, message, data, fileBytes, file_ext = createFunctionFromString(script.script)(*args,
                                                docType=doc.type,
                                                docText=doc.rawText,
                                                docName=doc.name,
                                                docByteObj=docBytes,
                                                logger=scriptLogger,
                                                scriptInputs=scriptInputs,
                                                previousData=transformed_data,
                                                **kwargs)

            logging.info(f"Finished {finished}")
            logging.info(f"Message {message}")
            logging.info(f"data {data}")
            logging.info(f"file extension {file_ext} of type {type(file_ext)}")

            # take file object and save to filesystem provided it is not none and plausibly could be an extension
            if file_ext and len(file_ext) > 1:
                name, file_extension = os.path.splitext(doc.name)
                file_data = ContentFile(fileBytes)
                result.file.save("./step_results/{0}/{1}/{2}-{3}.{4}".format(jobId, stepId, doc.id, name, file_ext),
                                 file_data)

            # Create object to hold our outputs (this helps with performance). They can get HUGE.
            # Storing them in the main result object really screws with performance.
            outputObj = ResultData.objects.create(
                output_data = json.dumps(data)
            )
            inputObj.save()

            result.output_data = outputObj
            result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            result.save()

            if finished:
                jobLogger.info(msg=log)
                return JOB_SUCCESS
            else:
                jobLogger.error(msg=log)
                return JOB_FAILED_DID_NOT_FINISH

        except Exception as err:

            jobLogger.error("Error on running JobDoc Script:")
            jobLogger.error(traceback.print_exc())

            message = "{0} - Error thrown by user script in applyPythonScriptToJobDoc for job #{1} doc #{2} script #{3}: {4}".format(
                JOB_FAILED_DID_NOT_FINISH, jobId, docId, scriptId, err)

            jobLogger.error(message)
            stopJob(jobId=jobId, status=message, error=True)
            result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            result.save()

            return message

    except Exception as e:
        message = "{0} - Error setting up step results for job #{1}, script #{2}: {3}".format(JOB_FAILED_DID_NOT_FINISH,
                                                                                              jobId, stepId, e)
        jobLogger.error(message)
        return message


# this should only be run by the public tasks in this file. It has more limited error handling as it assumes this was handled successfully earlier.
# processingTask is assumed to take arguments job and doc
@celery_app.task(base=FaultTolerantTask, name="Celery Wrapper for Python Job Task")
def applyPythonScriptToJob(*args, jobId=-1, stepId=-1, scriptId=-1, **kwargs):

    jobLogger = JobLogger(jobId=jobId, name="applyPythonScriptToJob")
    log = "applyPythonScriptToJob - jobId: {0}".format(jobId)
    log += "\napplyPythonScriptToJob - scriptId: {0}".format(scriptId)
    if len(args) > 0:
        log += "\napplyPythonScriptToJobDoc - args are: {0}".format(args)
        log += f"\nPrevious job succeeded: {jobSucceeded(args[0])}"
    log += "\napplyPythonScriptToJob - kwargs are: {0}".format(kwargs)

    if len(args) > 0 and not jobSucceeded(args[0]):
        message = "{0} - Preceding task failed for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId,
                                                                                    args[0])
        log += "\n" + message
        jobLogger.error(msg=log)
        stopJob(jobId=jobId, status=message, error=True)
        return message

    # Build the inputs for this script...
    try:
        job = Job.objects.get(id=jobId)
        step = PipelineStep.objects.get(id=stepId)
        script = PythonScript.objects.get(id=scriptId)

        # Build json inputs for job, which are built from both step settings in the job settings and
        # and the step_settings store.
        scriptInputs = buildScriptInput(step.step_number,
                                        job.job_inputs,
                                        step.step_settings,
                                        step.script.required_inputs)

        # If there was a preceding step, grab the data from that step and pass it as an input, otherwise, this is a
        # first (possibly only) step and we want to pass in job settings.
        preceding_data = {}
        try:

            preceding = Result.objects.filter(job=job, job_step__step_number=step.step_number - 1, type="STEP")
            log += "\nPreceding step results jobs are: "
            log += "\n" + str(preceding)

            if len(preceding) == 1:
                preceding = preceding[0].output_data.output_data
                try:
                    preceding_data = json.loads(preceding)
                except Exception as e:
                    log += f"\nFound preceding data and trying to load from json but encountered an error: {e}"
                    jobLogger.error(msg=log)
            else:
                log += f"\nIf there is preceding step data, the length of preceding step query set should be 1. It's {len(preceding)}"

        except Exception as e:
            log += f"\nTrying to build preceding data but encountered an unexpected error: {e}"

        log += "\nStarting data transform"
        # transform the scriptInputs (if there is a transform script provided)
        transformed_data = preceding_data
        if step.input_transform:
            transformed_data = transformStepInputs(step.input_transform, preceding_data)

        log += "\nData transform complete"

        result = Result.objects.create(
            name="Pipeline: {0} | Step #{1}".format(job.pipeline.name, step.script.name),
            job=job,
            job_step=step,
            type='STEP',
            input_settings=json.dumps(scriptInputs),
            start_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        result.save()

        # Create object to hold our inputs (this helps with performance). They can get HUGE.
        # Storing them in the main result object really screws with performance.
        inputObj = ResultInputData.objects.create(
            raw_input_data=json.dumps(preceding_data),
            transformed_input_data=json.dumps(transformed_data),
        )
        inputObj.save()

        # Link input data to the result
        result.input_data = inputObj
        result.save()

        # This will only get logs from within user's script if they actually use the logger.
        scriptLogger = TaskLogger(resultId=result.id, name="User_Job_Script")
        log += f"\nStarting script for job ID #{job.id} (step # {step.step_number}) with inputs: {scriptInputs}"

        try:
            # call the script with the appropriate Gremlin / Django objects already loaded (don't want the user
            # interacting with underlying Django infrastructure.
            finished, message, data, fileBytes, file_ext, docPackaging = createFunctionFromString(script.script)(*args,
                                                                                        job=job,
                                                                                        step=step,
                                                                                        logger=scriptLogger,
                                                                                        scriptInputs=scriptInputs,
                                                                                        previousData=transformed_data,
                                                                                        **kwargs)

            logging.info(f"Finished {finished}")
            logging.info(f"Message {message}")
            logging.info(f"data {data}")
            logging.info(f"file extension {file_ext} of type {type(file_ext)}")
            logging.info(f"doc packaging instructions are {docPackaging}")

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
                        print(f"newChildPath root is {Path(docPackaging[returnDocId])}")
                        newChildPath = f"{docPackaging[returnDocId]}/{docPath.name}"
                        print(f"newChildPath is {newChildPath}")
                        packageZip.writestr(newChildPath, file.read())

                packageZip.close()

                result.file.save("./step_results/{0}/{1}/Step {2} ({3}).{4}".format(jobId, stepId, step.name,
                                                                                    step.step_number+1, "zip"),
                                 ContentFile(packageBytes.getvalue()))

            #Otherwise, store the file object returned
            # take file object and save to filesystem provided it is not none and plausibly could be an extension
            elif file_ext and len(file_ext) > 1:
                file_data = ContentFile(fileBytes)
                result.file.save("./step_results/{0}/{1}/Step {2} ({3}).{4}".format(jobId, stepId, step.name,
                                                                                    step.step_number+1, file_ext),
                                 file_data)

            # Create object to hold our outputs (this helps with performance). They can get HUGE.
            # Storing them in the main result object really screws with performance.
            outputObj = ResultData.objects.create(
                output_data=json.dumps(data, indent=4)
            )
            outputObj.save()

            result.output_data = outputObj
            result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            result.save()

            if finished:

                # iterate job task completion count
                job.completed_tasks = job.completed_tasks + 1
                job.save()
                jobLogger.info(msg=log)

                return JOB_SUCCESS

            else:

                jobLogger.error(msg=log)
                return JOB_FAILED_DID_NOT_FINISH

        except Exception as err:

            jobLogger.error("Error on running Job Script:")
            jobLogger.error(traceback.print_exc())

            message = "{0} - Error thrown by user script in applyPythonScriptToJob for job #{1} script #{2}: {3}".format(
                JOB_FAILED_DID_NOT_FINISH, jobId, scriptId, err)
            log += "\n"+message
            jobLogger.error(log)

            stopJob(jobId=jobId, status=message, error=True)

            result.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
            result.save()

            return message

    except Exception as e:
        message = "{0} - Error setting up inputs for Step #{1}: {2}".format(JOB_FAILED_DID_NOT_FINISH, stepId, e)
        log += "\n"+message
        jobLogger.error(log)
        return message


# Apparently, celery will NOT let you chain two groups without automatically converting the groups to chords.
# This is not really desired and is killing my workflow... the workaround is to terminate each group in chain with this "chordfinisher"
# to nullify celery's conversion into chord and then you get behavior you want from chaining the groups.
# read more here:
# https://stackoverflow.com/questions/15123772/celery-chaining-groups-and-subtasks-out-of-order-execution
@celery_app.task(base=FaultTolerantTask)
def chordfinisher(previousMessage, *args, **kwargs):
    return previousMessage


# for now, does nothing other than echo args...
# the intent will be to package up all of the individual results data objs for a given step
# and pass them along to the next step
@celery_app.task(base=FaultTolerantTask)
def resultsMerge(*args, jobId=-1, stepId=-1, **kwargs):
    jobLogger = JobLogger(jobId=jobId, name="resultsMerge")

    log="\n######### Results Merge At End of Parallel Step:"

    for arg in args:
        jobLogger.info(arg)

    start_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    job = Job.objects.get(id=jobId)
    step = PipelineStep.objects.get(id=stepId)
    results = Result.objects.filter(job_step=step, job=job)
    log += "\nI am a results merger and I detect there are this many results: " + str(len(results))

    input_settings = {}
    transformed_inputs = {}
    raw_inputs = {}
    outputs = {}

    for result in results:
        log+=f"\nTry to package result for {result.name}"
        try:
            input_settings[f"{result.doc.id}"] = json.loads(result.input_settings)
        except Exception as e:
            log+=f"\nError while trying to input settings for step {result.job_step.step_number} and " \
                              f"doc {result.doc.id}: {e}"
            input_settings[f"{result.doc.id}"] = {}

        try:
            transformed_inputs[f"{result.doc.id}"] = json.loads(result.input_data.transformed_input_data)

        except Exception as e:

            log += f"\nError while trying to merge transformed input data for step {result.job_step.step_number} and doc {result.doc.id}: {e}"
            transformed_inputs[f"{result.doc.id}"] = {}

        try:
            raw_inputs[f"{result.doc.id}"] = json.loads(result.input_data.raw_input_data)

        except Exception as e:
            log += f"\nWARNING - Error while trying to merge raw input data for step {result.job_step.step_number} and " \
                   f"doc {result.doc.id}: {e}"
            raw_inputs[f"{result.doc.id}"] = {}

        try:
            outputs[f"{result.doc.id}"] = json.loads(result.output_data.output_data)
        except Exception as e:
            log += f"WARNING - Error while trying to merge output data for step {result.job_step.step_number} and " \
                f"doc {result.doc.id}: {e}"
            outputs[f"{result.doc.id}"] = {}

    # Create object to hold our inputs (this helps with performance). They can get HUGE.
    # Storing them in the main result object really screws with performance.
    inputObj = ResultInputData.objects.create(
        raw_input_data=json.dumps(raw_inputs),
        transformed_input_data=json.dumps(transformed_inputs),
    )
    inputObj.save()
    log+="\ninputObj saved."

    # Create object to hold our outputs (this helps with performance). They can get HUGE.
    # Storing them in the main result object really screws with performance.
    outputObj = ResultData.objects.create(
        output_data=json.dumps({"documents": outputs})
    )
    outputObj.save()
    log+="\noutputObj saved."

    step_result = Result.objects.create(
        name="Pipeline: {0} | Step #{1}".format(job.pipeline.name, step.script.name),
        job=job,
        job_step=step,
        type='STEP',
        input_data=inputObj,
        output_data=outputObj,
        start_time=start_time,
        stop_time=datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    step_result.save()

    log+="\Step result created and saved."

    # iterate job step completion count
    job.completed_tasks = job.completed_tasks + 1
    job.save()

    log+="\nResults merger complete."

    jobLogger.info(msg=log)

    return JOB_SUCCESS

@celery_app.task(base=FaultTolerantTask, name="Ensure Script is Available")
def prepareScript(*args, jobId=-1, scriptId=-1, **kwargs):

    try:
        if len(args) > 0 and not jobSucceeded(args[0]):
            message = "{0} - Preceding task failed for job Id {1}. Message: {2}".format(JOB_FAILED_DID_NOT_FINISH, jobId,
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
def installPackages(scriptId, *args, **kwargs):
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
def runPythonScriptSetup(scriptId, *args, **kwargs):
    print("run")
    log = "#################### Setup Script Log ####################\n\n{1}"

    try:
        # call pip as subprocess in current environment. Capture output using p.communicate()
        # based on: https://stackoverflow.com/questions/2502833/store-output-of-subprocess-popen-call-in-a-string
        print(args)
        for line in args:
            print(line.split())
            p = subprocess.Popen(line.split(), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = p.communicate()

            print(out)
            print(err)

            # Need to escape out the escape chars in the resulting string: https://stackoverflow.com/questions/6867588/how-to-convert-escaped-characters
            out = codecs.getdecoder("unicode_escape")(out)[0]
            err = codecs.getdecoder("unicode_escape")(err)[0]

            log = log + "\nSuccess:\n" + out + "\nErrors:\n" + err

            print(log)

        script = PythonScript.objects.get(id=scriptId)
        script.setup_log = script.setup_log + "\n\n" + log
        script.save()

        return "{0} - Package install: {1}".format(JOB_SUCCESS, out)

    except Exception as e:
        print(f"Error with install: {e}")
        return JOB_FAILED_DID_NOT_FINISH


# create a new package for a python script... can be imported dynamically later
@celery_app.task(base=FaultTolerantTask, name="Create New Package")
def createNewPythonPackage(scriptId, *args, **kwargs):
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

                elif file_extension == ".doc":
                    logger.info("Appending AND CONVERTING DOC: " + filename)

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

                elif file_extension == ".pdf":
                    logger.info("Appending AND CONVERTING PDF: " + filename)
                #
                # 	def printStyle(style):
                # 		sans_serif_str = ""
                # 		if style.IsSerif():
                # 			sans_serif_str = " sans-serif;"
                # 		rgb = style.GetColor()
                # 		rgb_hex = "%02X%02X%02X;" % (rgb[0], rgb[1], rgb[2])
                # 		font_str = '%g' % style.GetFontSize()
                # 		sys.stdout.write(" style=\"font-family:" + style.GetFontName() + "; font-size:"
                # 		                 + font_str + ";" + sans_serif_str + " color:#" + rgb_hex + "\"")
                #
                # 	def dumpAllText(reader):
                # 		element = reader.Next()
                # 		while element != None:
                # 			type = element.GetType()
                # 			if type == Element.e_text_begin:
                # 				print("Text Block Begin")
                # 			elif type == Element.e_text_end:
                # 				print("Text Block End")
                # 			elif type == Element.e_text:
                # 				bbox = element.GetBBox()
                # 				print("BBox: " + str(bbox.GetX1()) + ", " + str(bbox.GetY1()) + ", "
                # 				      + str(bbox.GetX2()) + ", " + str(bbox.GetY2()))
                # 				textString = element.GetTextString()
                # 				if sys.version_info.major >= 3:
                # 					textString = ascii(textString)
                # 				print(textString)
                # 			elif type == Element.e_text_new_line:
                # 				print("New Line")
                # 			elif type == Element.e_form:
                # 				reader.FormBegin()
                # 				dumpAllText(reader)
                # 				reader.End()
                # 			element = reader.Next()
                #
                # 	# A utility method used to extract all text content from
                # 	# a given selection rectangle. The recnagle coordinates are
                # 	# expressed in PDF user/page coordinate system.
                # 	def ReadTextFromRect(page, pos, reader):
                # 		reader.Begin(page)
                # 		srch_str = RectTextSearch(reader, pos)
                # 		reader.End()
                # 		return srch_str
                #
                # 	# A helper method for ReadTextFromRect
                # 	def RectTextSearch(reader, pos):
                # 		element = reader.Next()
                # 		srch_str2 = ""
                # 		while element != None:
                # 			type = element.GetType()
                # 			if type == Element.e_text:
                # 				bbox = element.GetBBox()
                # 				if (bbox.IntersectRect(bbox, pos)):
                # 					arr = element.GetTextString()
                # 					srch_str2 += arr
                # 					srch_str2 += "\n"
                # 			elif type == Element.e_text_new_line:
                # 				None
                # 			elif type == Element.e_form:
                # 				reader.FormBegin()
                # 				srch_str2 += RectTextSearch(reader, pos)
                # 				print(srch_str2)
                # 				reader.End()
                # 			element = reader.Next()
                # 		return srch_str2
                #
                # 	# Note that you don't need to read a whole image at a time. Alternatively
                # 	# you can read a chuck at a time by repeatedly calling reader.Read(buf, buf_sz)
                # 	# until the function returns 0.
                #
                # 	def ProcessElements(reader):
                #
                # 		text = ""
                #
                # 		element = reader.Next()  # Read page contents
                # 		while element != None:
                # 			type = element.GetType()
                # 			if type == PDFNetPython.Element.e_path:  # Process path data...
                # 				ProcessPath(reader, element)
                # 			elif type == PDFNetPython.Element.e_text_begin:  # Process text block...
                # 				newStr = ProcessText(reader)
                # 				if isinstance(newStr, str):
                # 					text = text + newStr
                # 			elif type == PDFNetPython.Element.e_form:  # Process form XObjects
                # 				reader.FormBegin()
                # 				ProcessElements(reader)
                # 				reader.End()
                # 			elif type == PDFNetPython.Element.e_image:  # Process Images
                # 				ProcessImage(element)
                # 			element = reader.Next()
                #
                # 		return text
                #
                # 	doc_text = ""
                # 	doc = PDFNetPython.PDFDoc(filename)
                # 	doc.InitSecurityHandler()
                # 	pgnum = doc.GetPageCount()
                # 	page_begin = doc.GetPageIterator()
                #
                # 	for i in range(1, pgnum):
                # 		logger.info("Extracting pdf text for page {0} of {1}".format(i, pgnum))
                # 		page = doc.GetPage(i)
                #
                # 		if page == None:
                # 			logger.warning("Page #{0} not found".format(i))
                #
                # 		else:
                # 			logger.info("EXTRACT - From Pdf page #{0}".format(i))
                # 			txt = TextExtractor()
                # 			txt.Begin(page)  # Read the page
                # 			txtAsText = txt.GetAsText()
                # 			if sys.version_info.major >= 3:
                # 				txtAsText = ascii(txtAsText)
                #
                # 			# there were lots of escape chars in the pdftron text...
                # 			# This SO https://stackoverflow.com/questions/4020539/process-escape-sequences-in-a-string-in-python
                # 			# recommended the following to "decode" the escapes.
                # 			decoded_string = bytes(txtAsText, "utf-8").decode("unicode_escape")
                # 			doc_text = doc_text + decoded_string
                #
                # 			doc_text = doc_text + txtAsText
                #
                # 	doc.Close()
                #
                # 	d.rawText = doc_text
                    d.extracted = True
                    d.save()

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
        logger.info("Job #{0} has {1} step results and {2} results total.".format(jobId, len(stepResults), len(allResults)))

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
                        newChildPath = "./Step {0} ({1})/{2}".format(r.job_step.step_number+1, r.job_step.name, zip_filename)
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
                    stepData = json.loads(r.output_data.output_data)
                    jobData = {**jobData, **{r.job_step.step_number: stepData}}
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

        # Create object to hold our outputs (this helps with performance). They can get HUGE.
        # Storing them in the main result object really screws with performance.
        outputObj = ResultData.objects.create(
            output_data=json.dumps(jobData),
        )
        outputObj.save()

        result = Result.objects.create(
            name="Job {0}".format(jobId),
            job=job,
            type='JOB',
            output_data=outputObj
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
