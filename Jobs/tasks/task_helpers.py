import io
import logging

from django.conf import settings
from django.core.files.storage import default_storage

from .task_constants import JOB_SUCCESS
from ..models import *
from datetime import datetime
import ast
import copy
import importlib
import json
import jsonschema
import requests
import re
import types
import textwrap

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ScriptLogger:

    def __init__(self, scriptId, jobId, stepId, resultId):
        self.__scriptId = scriptId
        self.__jobId = jobId
        self.__stepId = stepId
        self.__resultId = resultId
        self.log = ""

    def info(self, message):
        try:
            labelledMessage = "INFO - Job {0} / Step {1} / Script {2}: {3}".format(self.__jobId, self.__stepId,
                                                                                   self.__scriptId, message)
            self.log = ((self.log + "\n") if self.log != "" else "") + labelledMessage
            logger.info(labelledMessage)
        except Exception as e:
            logger.error("Error trying to store user script logs: {0}".format(e))

    def error(self, message):
        try:
            labelledMessage = "ERROR - Job {0} / Step {1} / Script {2}: {3}".format(self.__jobId, self.__stepId,
                                                                                    self.__scriptId, message)
            self.log = ((self.log + "\n") if self.log != "" else "") + labelledMessage
            logger.error(labelledMessage)

        except Exception as e:
            logger.error("Error trying to store user script logs: {0}".format(e))

    def warn(self, message):
        try:
            labelledMessage = "WARNING - Job {0} / Step {1} / Script {2}: {3}".format(self.__jobId, self.__stepId,
                                                                                      self.__scriptId, message)
            self.log = ((self.log + "\n") if self.log != "" else "") + labelledMessage
            logger.warning(labelledMessage)

        except Exception as e:
            logger.error("Error trying to store user script logs: {0}".format(e))


# Given a
def isSuccessMessage(message):
    end = len(JOB_SUCCESS)
    return message[0:end] == JOB_SUCCESS


# Can be used to combine arrays but only add unique items from addArray to targetArray.
def addUniquesToArray(targetArray, addArray):
    seen = set(targetArray)
    for item in addArray:
        if item not in seen:  # faster than `word not in output`
            seen.add(item)
            targetArray.append(item)
    return targetArray

#Given the node we want to stop with in a digraph, work backwards and build a sequential list of all of the nodes
#That need to run in order to feed data to the target node (for pipeline builder)
def buildPipelineToTargetNode(pipeline, targetNode):
    nodes = []


def getPrecedingNodesForNode(pipeline, targetNode):

    logger.info(f"Spinning up getPrecedingNodesForNode with pipeline {pipeline} and targetNode {targetNode}")

    try:

        nodes = []
        in_edges = Edge.objects.filter(end_node=targetNode, parent_pipeline=pipeline).prefetch_related('start_node')

        logger.info(f"In edges are {in_edges}")

        if in_edges.count() > 0:
            for e in in_edges:
                logger.info(f"Get parents of node {e}")
                nodes = [*getPrecedingNodesForNode(pipeline, e.start_node), *nodes]

        nodes = [*nodes, targetNode]

        logger.info(f"Resulting nodes are: {nodes}")

        return nodes

    except Exception as err:
        logger.error(f"Error building nodes: {err}")
        return []

def buildNodePipelineRecursively(pipeline, node=None):

    print(f"buildNodePipelineRecursively for node {node} for pipeline {pipeline}")

    try:

        nodes = []
        pipelineNodes = []

        if not node:
            root_node = pipeline.root_node
        else:
            root_node = node

        if not root_node:
            logger.error(f"Error trying to build array of pipeline nodes - "
                         f"it appears there is no root node for this pipeline.")
            return []

        in_edges = Edge.objects.filter(end_node=root_node, parent_pipeline=pipeline).prefetch_related('start_node')
        out_edges = Edge.objects.filter(start_node=root_node, parent_pipeline=pipeline).prefetch_related('end_node')

        for e in in_edges:
            pipelineNodes.append(e.start_node)
        print(f"Finished edge assembly: {pipelineNodes}")

        if out_edges.count() == 0:
            pipelineNodes.append(root_node)
        else:
            for e in out_edges:
                nodes.append(buildNodePipelineRecursively(pipeline, node=e.end_node))

        print(f"Finished out_edge traversal: {nodes}")

        for node in nodes:
            addUniquesToArray(pipelineNodes, node)

        print(f"Final node array: {pipelineNodes}")

    except Exception as e:
        print(f"Error trying to buildNodePipelineRecursively: {e}")
        pipelineNodes = []

    return pipelineNodes


def sendCallback(job):
    try:
        logger.info("There is a callback... preparing to make callback")

        result = Result.objects.get(job=job, type='JOB')

        usingS3 = (settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")
        if usingS3:
            filename = result.file.name
        else:
            filename = result.file.path

        fileBytes = None
        data = {}

        if result:
            with default_storage.open(filename, mode='rb') as file:
                fileBytes = io.BytesIO(file.read()).getvalue()

            data = result.output_data.output_data

        returnObj = {
            'jobId': job.id,
            'status': job.status,
            'data': data,
        }

        print(f"returnObj: {returnObj}")
        files = {'file': ('results.zip', fileBytes, 'application/zip', {'Expires': '0'})}

        x = requests.post(job.callback, data=returnObj, files=files)
    except Exception as e:
        logger.warn(f"Error on trying to send callback on job completion: {e}")


# given a stepId, return a list of the preceding nodes
def getPrecedingNodes(nodeId, ids_only=False):
    try:

        # First get the edges pointing to this node and prefetch the start_nodes
        precedents = Edge.objects.filter(end_node__id=nodeId).prefetch_related('start_node')

        nodes = []

        # Now, build a list of the start_nodes for each edge pointing to nodeId
        for p in precedents:
            if ids_only:
                nodes.append(p.start_node.id)

            else:
                nodes.append(p.start_node)

        return nodes

    except Exception as e:
        return []


def getPrecedingResults(job, node):
    #TODO - somehow this error: Error trying to get preceding results for node 7: Field 'id' expected a number but got [3].

    print(f"getPrecedingResults for job{job} node {node}")

    try:
        previous_data = {}

        preceding_nodes = getPrecedingNodes(node.id, ids_only=True)
        print(f"preceding_nodes is {preceding_nodes}")

        for pn in preceding_nodes:
            pr = Result.objects.get(job=job, pipeline_node__id=pn)
            previous_data[pr.pipeline_node.id] = json.loads(pr.output_data)

        return previous_data

    except Exception as e:
        logger.error(f"Error trying to get preceding results for node {node.id}: {e}")
        return {}


# Given a pipeline id, traverse the pipeline tree and produce a json that user can use to scaffold up
def getPipelineInputJSONTemplate(pipelineId):
    try:

        schemaTemplate = {}
        nodes = PipelineNode.objects.order_by('id').filter(parent_pipeline__id=pipelineId)\
            .prefetch_related('out_edges', 'in_edges')

        for n in nodes:
            schemaTemplate[n.id] = {
                "Name": n.name,
                "Type": n.type,
                "Inputs": json.loads(n.step_settings)
            }

        return schemaTemplate

    except Exception as e:
        return {}


# Given a job and a step id, look up the job inputs, step inputs and assemble combined inputs, always overwriting
# script-level settings with step-level settings and, finally, with job-level settings
def buildScriptInput(pipeline_node, job, script):

    print(f"buildScriptInput for node: {pipeline_node}")

    scriptInputs = {}

    # First try to get the node settings
    try:
        print(f"Script settings: {pipeline_node.step_settings}")
        scriptInputs = json.loads(pipeline_node.step_settings) #TODO - Why is this type string?
        print(f"scriptInputs: {scriptInputs} of type {type(scriptInputs)}")
    except:
        pass

    # Try to get the job settings for this step, which should be stored as valid json string in the json_inputs field.
    # The inputs should be stored in the job in a json object of form { schema : [ step_1_schema, step_2_schema, etc.] }
    # Try to load the job inputs, which should be stored as valid json string in the json_inputs field.
    try:
        jobInputs = json.loads(job.job_inputs)
        print(f"Job Inputs: {jobInputs}")
        print(f"jobInputs type is: {type(jobInputs)}")
        print(f"Current pipeline node id is: {pipeline_node.id}")
        print(f"Pipeline node id type: {type(pipeline_node.id)}")
        str_id = f"{pipeline_node.id}" #TODO - why is this weird half-way conversion of the dict happening.
        print(f"This nodes schema obj is: {jobInputs[str_id]}")
        jobInputs = jobInputs[str_id]['schema']
        print(f"Mark job input: {jobInputs} of type {type(jobInputs)}")
    except:
        jobInputs = {}

    # Try to combine the two, overwriting step settings with job settings if there's a collision:
    scriptInputs = {**scriptInputs, **jobInputs}
    print(f"Inputs merged: {scriptInputs}")

    # Check that the compiled schema works
    try:
        # also check that the inputs are valid for the schema
        schema = json.loads(script.schema)
        logger.info(f"Schema loaded: {schema}")
        try:
            jsonschema.validate(scriptInputs, schema)
            logger.info(f"Schema check passed for inputs:\n{scriptInputs}")
            return scriptInputs
        except Exception as e:
            logger.warning(f"Schema check failed for inputs:\n{scriptInputs}")
            pass
    except Exception as e:
        logger.error("Couldn't test schema. Error: {0}".format(e))
        pass

    return {}


# for jobs that branch (run in parallel), you get back an array of their return message, so you need to test for
# an array of success messages in these cases. If there is a failure amongst a group a successes, currently,
# entire execution is considered a failure.
def jobSucceeded(previousMessage):
    if isinstance(previousMessage, list):
        if filter(isSuccessMessage, previousMessage):
            return True
        return False
    else:
        if previousMessage == JOB_SUCCESS:
            return True
        return False


# Given a job id, stop the job and pass along status and/or error
def stopJob(jobId=-1, status="N/A", error=False):
    # This arg "extractStatus" gets passed in via the celery chain command as the behavior for that call is to run
    # each task in order, left to right, and passing the return value from the most recently finished task to the
    # next task. So, if we called chain(extractText.s(), extractEntitiesFromJob.s(jobId)), extractEntities would get two
    # arguments in fact, the boolean return value of extractText.s().
    if jobId == -1:
        logger.error("No job ID was specified for runJobGremlin. You must specify a jobId.")
        return False

    elif len(Job.objects.filter(id=jobId)) != 1:
        logger.error("There appears to be no job with jobId = {0}.".format(jobId))
        return False

    else:
        job = Job.objects.get(id=jobId)
        job.status = status
        job.error = error
        job.finished = True
        job.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        job.save()

        #Check if there's a job result obj, and, if so, set to finished
        jobResult = Result.objects.get(job_id=jobId, type=Result.JOB)
        if jobResult:
            if not jobResult.error and not jobResult.finished:
                jobResult.error=error
                jobResult.finished=True
                jobResult.stop_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
                job.save()

        # If there's a callback... send signal that job is complete.
        if job.callback != "":
            sendCallback(job)


# given a bytes object, a job, a script, and a step, save file to filesystem and store in result
# if doc is None, name file after job and expect only one file for job, otherwise name after doc
# and expect one per doc.
def saveTaskFile(bytesObj=None, fileExt=".zip", job=None, script=None, doc=None, result=None):
    # For this doc, create a new zip archive in memory, prepare to add docs to it.
    # Create a zipfile for the batch
    resultFileDir = "./jobs_data/%s/result %s/" % (job.id, result.id)

    if doc:
        resultFilename = "{0} - {1}{2}".format(doc.name, script.name, fileExt)
    else:
        resultFilename = "{0} - {1}{2}".format(job.name, script.name, fileExt)

    # Create directories for cluster results if it doesn't exist
    if not os.path.exists(resultFileDir):
        os.makedirs(resultFileDir)

    with open(resultFilename, 'wb+') as out:  ## Open temporary file as bytes
        out.write(bytesObj)

    if (doc):
        result.file = resultFilename
        result.save()
    else:
        job.file = resultFilename
        job.save()

    return resultFilename


# https://stackoverflow.com/questions/33409207/how-to-return-value-from-exec-in-function
def convertExpr2Expression(Expr):
    Expr.lineno = 0
    Expr.col_offset = 0
    result = ast.Expression(Expr.value, lineno=0, col_offset=0)
    return result


# https://stackoverflow.com/questions/33409207/how-to-return-value-from-exec-in-function
def exec_with_return(code):
    code_ast = ast.parse(code)

    init_ast = copy.deepcopy(code_ast)
    init_ast.body = code_ast.body[:-1]

    last_ast = copy.deepcopy(code_ast)
    last_ast.body = code_ast.body[-1:]

    exec(compile(init_ast, "<ast>", "exec"), globals())
    if type(last_ast.body[0]) == ast.Expr:
        return eval(compile(convertExpr2Expression(last_ast.body[0]), "<ast>", "eval"), globals())
    else:
        exec(compile(last_ast, "<ast>", "exec"), globals())


# This will take the string value of pipeline step field input_transform, expecting it to be a function called
# transform which will take a single argument ("input_data") and return a json object. It will use Python
# exec to do this and limit exec imports to just json and regex (re). This is to help plug security holes.
# unlike scripts which have global access to entire Gremlin system, pipeline step mappings could potentially
# have many more authors, so we need to be careful what we let people do in here.
# See here for guidance on limiting exec: https://www.programiz.com/python-programming/methods/built-in/exec
# See here for guidance on loading string code as module: https://stackoverflow.com/questions/55905240/python-dynamically-import-modules-code-from-string-with-importlib
def transformStepInputs(code_string, input_data):  # create blank module

    try:
        module = types.ModuleType("transform")

        # Code - going to take the code_string (which shouldn't concern itself with imports or functions) and wrap
        # it in proper imports we guarantee will be available for transforms
        code_template = """import json, re\n\ndef transform(input_data):\n\n{0}"""

        # populate the module with code (load the module dict as locals and be very specific about globals
        # more guidance on this can be found here: https://www.programiz.com/python-programming/methods/built-in/exec
        # basically, this prevents someone from trying to load a bunch of modules in their transform string and
        # relying on us blindly importing them. This should be very simply manipulation of json objects only...
        # do not want any other libraries... so passing in global of json and re will limit underlying code from
        # importing anything other than json and re (and relying on builtins).
        exec(code_template.format(textwrap.indent(code_string, '\t')), {'json': json, 're': re}, module.__dict__)
        return module.transform(input_data)

    except Exception as e:
        logger.error("ERROR - Input transform failed: {0}".format(e))
        return input_data


def createFunctionFromString(functionString):
    try:
        module = types.ModuleType("script")

        # populate the module with code (load the module dict as locals and be very specific about globals
        # more guidance on this can be found here: https://www.programiz.com/python-programming/methods/built-in/exec
        # basically, this prevents someone from trying to load a bunch of modules in their transform string and
        # relying on us blindly importing them. This should be very simply manipulation of json objects only...
        # do not want any other libraries... so passing in global of json and re will limit underlying code from
        # importing anything other than json and re (and relying on builtins).
        exec(functionString, module.__dict__)
        return module.pythonFunction

    except Exception as e:
        logger.error("Error loading script: {0}".format(e))
        return None


def returnScriptMethod(scriptId):
    logger.info("Starting returnScriptMethod for scriptId={0}".format(scriptId))

    try:
        script = PythonScript.objects.get(id=scriptId)
        logger.info("Fetched script:{0}".format(script.name))
        moduleToLoad = 'Jobs.tasks.scripts.{0}.{1}'.format(script.name, script.name)
        logger.info("Try to load module: {0}".format(moduleToLoad))
        mod = importlib.import_module(moduleToLoad)
        logger.info("Loaded module: {0}".format(mod))
        return getattr(mod, "pythonFunction")

    except Exception as e:
        logger.error("ERROR on returnScriptMethod({0}): {1}".format(e, scriptId))
        return None
