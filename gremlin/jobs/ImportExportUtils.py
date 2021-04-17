"""
Gremlin - The open source legal engineering platform
Copyright (C) 2020-2021 John Scrudato IV ("JSIV")

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/
"""

import json
import io
import logging
import zipfile
import base64
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString
from celery import chain
from django.conf import settings
from django.core.files.storage import default_storage
from .models import PythonScript, PipelineNode, Edge, Pipeline
from gremlin.jobs.tasks.tasks import importScriptsFromYAML, importNodesFromYAML, importEdgesFromYAML, unlockPipeline, \
    linkRootNodeFromYAML, runScriptEnvVarInstaller, runScriptSetupScript, runScriptPackageInstaller, \
    unlockScript, lockScript
from gremlin.jobs.tasks.built_in_tasks import loadDataFilesFromZipBytes

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

        print("Try exportScriptYAMLObj()")

        script = PythonScript.objects.get(pk=scriptId)

        print("Fetched script obj")

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

        print("Start data")

        data = {
            'id': script.id,
            'data_file': f"{script.data_file.uuid}" if script.data_file else None,
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

        print(f"data: {data}")

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


def exportPipelineToZip(pipelineId):

    try:

        usingS3 = (
                settings.DEFAULT_FILE_STORAGE == "gremlin.utils.storages.MediaRootS3Boto3Storage")

        pipeline = Pipeline.objects.select_related('root_node').get(pk=pipelineId)
        print("Fetched pipeline obj...")

        nodes = []
        edges = []
        scripts = {}
        script_dict = {}

        zip_bytes = io.BytesIO()
        myYaml = io.StringIO()

        yaml = YAML()
        yaml.preserve_quotes = False

        zip_file = zipfile.ZipFile(zip_bytes, mode='w', compression=zipfile.ZIP_DEFLATED)
        print("Zip file created")

        for node in PipelineNode.objects.filter(parent_pipeline=pipeline):

            print(f"Look over {node}")

            if node.script:

                print(f"Node ID {node.script.id} has script: {node.script}")
                print(f"Scripts was: {script_dict}")

                script_dict[node.script.id] = exportScriptYAMLObj(node.script.id)

                print(f"Script YAML created...")

                if node.script.data_file and node.script.data_file.data_file:

                    print("Script had a data file")

                    # THe precise field with the valid filename / path depends on the storage adapter, so handle accordingly
                    if usingS3:
                        filename = node.script.data_file.data_file.name

                    else:
                        filename = node.script.data_file.data_file.path

                    data_file_bytes = default_storage.open(filename, mode='rb').read()
                    zip_file.writestr(f"/data/{node.script.data_file.uuid}.zip", data_file_bytes)

        scripts = list(script_dict.values())

        print(f"Scripts are: {scripts}")

        for edge in Edge.objects.filter(parent_pipeline=pipeline):
            edges.append(exportPipelineEdgeToYAMLObj(edge.id))
        print("Edges converted to YAML")

        for node in PipelineNode.objects.filter(parent_pipeline=pipeline):
            nodes.append(exportPipelineNodeToYAMLObj(node.id))
        print("Nodes converted to YAML")

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

        print("Dump YAML")
        yaml.dump(data, myYaml)

        zip_file.writestr("pipeline_export.yaml", myYaml.getvalue())
        zip_file.close()
        zip_bytes.seek(io.SEEK_SET)

        print("Done with zip_bytes... returning")

        return zip_bytes

    except Exception as e:
        print(f"Error exporting Pipeline to archive: {e}")
        return None


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
# however, and related scripts, nodes, edges AND data files get created asynchronously.
def importPipelineFromZip(zip_bytes, owner):

    try:

        pipeline_zip = zipfile.ZipFile(io.BytesIO(zip_bytes))
        print(f"Zip contents: {pipeline_zip.namelist()}")
        yaml_string = pipeline_zip.read('pipeline_export.yaml')

        yaml = YAML()
        data = yaml.load(yaml_string)

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

        # NOTE: these are not running here... we're assembling a sequence of celery tasks which will be injected
        # into the appropriate place in a larger, more complex setup pipeline. Use of asynchronous workers is to
        # account for potentially long-running setup tasks and complex pipelines that, in theory have no limit on
        # complexity. This provides some protection over having this live entirely in the views.
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

        # Bytes can be serialized as JSON but requires some encoding and decoding.
        # Check this post:
        encoded_zip_bytes = base64.b64encode(zip_bytes)  # b'ZGF0YSB0byBiZSBlbmNvZGVk' (notice the "b")
        ascii_zip_bytes_string = encoded_zip_bytes.decode('ascii')

        # Setup all the relationships asynchronously, otherwise this request could take forever to complete
        # I originally tried to make script_setup_steps a group of chains, where the four script setup tasks
        # for each script (runScriptEnvVarInstaller, runScriptSetupScript, runScriptPackageInstaller and unlockScript)
        # would be a short but, if there were multiple script, the different script assembly groups would be grouped
        # and run in parallel if worker bandwidth were available. Unfortunately, I ran into a weird issue where I had a
        # task that created and launched these chords yet it seemed to run twice and the second call to it would break
        # as it didn't have arguments. Never figured it out and didn't want that to delay the release. This version obv
        # does everything in serial, so it's slower, but it doesn't seem to be an issue for now and I expect imports
        # to be rare. Can work on improving this later if performance becomes as issue.
        chain([
            loadDataFilesFromZipBytes.si(ascii_zip_bytes_string=ascii_zip_bytes_string),
            importScriptsFromYAML.s(scripts=data['scripts'], ownerId=owner.id),
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
