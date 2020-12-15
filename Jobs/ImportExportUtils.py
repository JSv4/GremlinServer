import json
import logging
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from celery import chain
from .models import PythonScript, PipelineNode, Edge, Pipeline
from Jobs.tasks.tasks import importScriptsFromYAML, importNodesFromYAML, importEdgesFromYAML, unlockPipeline, \
    linkRootNodeFromYAML, runScriptEnvVarInstaller, runScriptSetupScript, runScriptPackageInstaller, \
    unlockScript, lockScript

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

#######################################################################################################################
##  Script Exporter
#######################################################################################################################

# HUGE thanks to Ruamel.yaml for making a more user friendly Python YAML library AND for this SO post
# https://stackoverflow.com/questions/50852735/how-to-use-ruamel-yaml-to-dump-literal-scalars
# Which gave me a point in the right direction to figure out to use a literal scalar.
def exportScriptYAMLObj(scriptId):

    try:

        script = PythonScript.objects.get(pk=scriptId)

        supported_file_types = ['*']
        try:
            supported_file_types = json.loads(script.supported_file_types)
        except Exception as e:
            logger.error(f"Error trying to parse supported_file_types for script ID #{script.id}: {e}")

        env_variables = {'test': 'test'}
        try:
            env_variables=json.loads(script.env_variables)
        except Exception as e:
            logger.error(f"Error trying to parse env_variables for script ID #{script.id}: {e}")

        data = {
            'id': script.id,
            'name': script.name,
            'human_name': script.human_name,
            'description': LiteralScalarString(script.description),
            'type': script.type,
            'supported_file_types': supported_file_types,
            'script': LiteralScalarString(script.script),
            'required_packages': LiteralScalarString(script.required_packages),
            'setup_script': LiteralScalarString(script.setup_script),
            'env_variables': env_variables,
            'schema': LiteralScalarString(script.schema)
        }

        return data

    except Exception as e:
        print(f"Error exporting script YAML: {e}")
        return {}

def exportPipelineNodeToYAMLObj(pythonNodeId):

    try:

        node = PipelineNode.objects.select_related('script').get(pk=pythonNodeId)

        step_settings = {}
        try:
            step_settings = json.loads(node.step_settings)
        except Exception as e:
            logger.error(f"Error trying to parse step_settings for node ID #{node.id}: {e}")

        data = {
            'id': node.id,
            'name': node.name,
            'script': node.script.id if node.script else None,
            'type': node.type,
            'input_transform': LiteralScalarString(node.input_transform),
            'step_settings': step_settings,
            'x_coord': node.x_coord,
            'y_coord': node.y_coord
        }

        return data

    except Exception as e:
        print(f"Error exporting PythonNode to YAML: {e}")
        return {}


def exportPipelineEdgeToYAMLObj(pythonEdgeId):

    try:

        edge = Edge.objects.get(pk=pythonEdgeId)

        data = {
            'id': edge.id,
            'label': edge.label,
            'start_node': edge.start_node.id,
            'end_node': edge.end_node.id,
            'transform_script': LiteralScalarString(edge.transform_script)
        }

        return data

    except Exception as e:
        print(f"Error exporting Pipeline Edge to YAML: {e}")
        return {}

def exportPipelineToYAMLObj(pipelineId):

    try:

        pipeline = Pipeline.objects.select_related('root_node').get(pk=pipelineId)

        nodes = []
        edges = []
        scripts = {}

        for node in PipelineNode.objects.filter(parent_pipeline=pipeline):
            print("Node:")
            print(node)
            if node.script:
                scripts[node.script.id] = exportScriptYAMLObj(node.script.id)

        scripts = list(scripts.values())

        for edge in Edge.objects.filter(parent_pipeline=pipeline):
            edges.append(exportPipelineEdgeToYAMLObj(edge.id))

        for node in PipelineNode.objects.filter(parent_pipeline=pipeline):
            nodes.append(exportPipelineNodeToYAMLObj(node.id))

        pipeline_meta = {
            'name': pipeline.name,
            'description': LiteralScalarString(pipeline.description),
            'root_node': pipeline.root_node.id,
            'scale': pipeline.scale,
            'x_offset': pipeline.x_offset,
            'y_offset': pipeline.y_offset,
        }

        data = {
            'pipeline': pipeline_meta,
            'scripts': scripts,
            'edges': edges,
            'nodes': nodes,
        }

        return data

    except Exception as e:
        print(f"Error exporting Pipeline Edge to YAML: {e}")
        return {}

# WARNING - this runs asynchronously. It creates pipeline syncrhonously and returns the pipeline data. The pipeline locked,
# however, and related scripts, nodes and edges get created asynchronously.
def importPipelineFromYAML(yamlString, owner):

    try:
        yaml = YAML()
        data = yaml.load(yamlString)

        print("Loaded import data")
        print(data)

        parent_pipeline = Pipeline.objects.create(
            owner=owner,
            locked=True,
            imported=True,
            name=data['pipeline']['name'],
            description=data['pipeline']['description'],
            scale=data['pipeline']['scale'],
            x_offset=data['pipeline']['x_offset'],
            y_offset=data['pipeline']['y_offset']
        )

        print("Created pipeline synchronously... Then lock object and run setup steps async.")

        script_setup_steps = []
        for script in data['scripts']:
            script_setup_steps.extend([
                lockScript.s(oldScriptId=script['id']),
                runScriptEnvVarInstaller.s(oldScriptId=script['id']),
                runScriptSetupScript.s(oldScriptId=script['id']),
                runScriptPackageInstaller.s(oldScriptId=script['id']),
                unlockScript.s(oldScriptId=script['id'], installer=True)
            ])

        print("Setup scripts:")
        print(script_setup_steps)

        # Setup all the relationships asynchronously, otherwise this request could take forever to complete
        # I originally tried to make script_setup_steps a group of chains, where the four script setup tasks
        # for each script (runScriptEnvVarInstaller, runScriptSetupScript, runScriptPackageInstaller and unlockScript)
        # would be a short but, if there were multiple script, the different script assembly groups would be grouped
        # and run in parallel if worker bandwidth were available. Unfortunately, I ran into a weird issue where I had a
        # task that created and launched these chords yet it seemed to run twice and the second call to it would break
        # as it didn't have arguments. Never figured it out and didn't want that to delay the release. This version obv
        # does everything in serial, so it's slower in theory, but these things execute pretty quickly and I expect imports
        # to be rare. Can work on improving this later.
        chain([
            importScriptsFromYAML.si(scripts=data['scripts'], ownerId=owner.id),
            importNodesFromYAML.s(nodes=data['nodes'], parentPipelineId=parent_pipeline.id, ownerId=owner.id),
            importEdgesFromYAML.s(edges=data['edges'], parentPipelineId=parent_pipeline.id, ownerId=owner.id),
            linkRootNodeFromYAML.s(pipeline_data=data['pipeline'], parentPipelineId=parent_pipeline.id),
            *script_setup_steps,
            unlockPipeline.s(pipelineId=parent_pipeline.id)
        ]).apply_async()

        return parent_pipeline

    except Exception as e:
        print(f"Error trying to import new pipeline: {e}")
        return None
