import json
import logging
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from pyaml import unicode
from yaml.representer import SafeRepresenter
from .models import PythonScript, PipelineNode, Edge, Pipeline

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

def importPipelineFromYAML(yamlString):

    try:
        yaml = YAML()
        data = yaml.load(yamlString)

        print("Loaded data")
        print(data)

        script_lookup = {}
        node_lookup = {}

        parent_pipeline = Pipeline.objects.create(
            name=data['pipeline']['name'],
            description=data['pipeline']['description'],
            scale=data['pipeline']['scale'],
            x_offset=data['pipeline']['x_offset'],
            y_offset=data['pipeline']['y_offset']
        )

        print("Created pipeline: ")
        print(parent_pipeline)

        for script in data['scripts']:
            print("Handle script:")
            print(script)

            new_script = PythonScript.objects.create(
                name=script['name'],
                human_name=script['human_name'],
                description=script['description'],
                type=script['type'],
                supported_file_types=script['supported_file_types'],
                script=script['script'],
                required_packages=script['required_packages'],
                setup_script=script['setup_script'],
                env_variables=script['env_variables'],
            )

            # Need to map the id in the YAML file to the id actually created by Django as there's almost no chance they'll be the same
            script_lookup[script['id']] = new_script

            print(f"New script created: {new_script}")

        # Create the nodes
        for node in data['nodes']:
            print("Handle node:")
            print(node)

            new_node = PipelineNode.objects.create(
                name=node['name'],
                script=script_lookup[node['script']] if node['script'] else None,
                type=node['type'],
                input_transform=node['input_transform'],
                step_settings=json.dumps(node['step_settings']),
                x_coord=node['x_coord'],
                y_coord=node['y_coord'],
                parent_pipeline=parent_pipeline
            )

            node_lookup[node['id']] = new_node

            print (f"New node created: {new_node}")

        # Go back to the pipeline object and link the root_node field to the appropriate new node obj (we needed to create
        # the object first so we had the id and could properly refer the two
        parent_pipeline.root_node=node_lookup[data['pipeline']['root_node']]
        parent_pipeline.save()

        # Create the edges
        for edge in data['edges']:

            print("Handle Edge:")
            print(edge)

            new_edge = Edge.objects.create(
                label=edge['label'],
                start_node=node_lookup[edge['start_node']],
                end_node=node_lookup[edge['end_node']],
                transform_script=edge['transform_script'],
                parent_pipeline=parent_pipeline
            )

            print(f"New edge created: {new_edge}")

        return parent_pipeline

    except Exception as e:
        print(f"Error trying to import new pipeline: {e}")
        return None
