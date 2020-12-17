from __future__ import absolute_import, unicode_literals

import celery, logging, zipfile

from django.core.files.base import ContentFile
from django.db import connection
from config import celery_app
from celery import chain, group, chord
from django.conf import settings
from django.core.files.storage import default_storage
from datetime import datetime

from Jobs.tasks.task_helpers import FaultTolerantTask
from Jobs.models import ScriptDataFile

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class FaultTolerantTask(celery.Task):
    """ Implements after return hook to close the invalid connection.
    This way, django is forced to serve a new connection for the next
    task.
    """
    abstract = True

    def after_return(self, *args, **kwargs):
        connection.close()


@celery_app.task(base=FaultTolerantTask, name="Calculate data file manifest")
def calculateDataFileManifest(*args, script_data_file_uuid=-1, **kwargs):

    try:

        data_model = ScriptDataFile.objects.get(uuid=script_data_file_uuid)

        # Check storage type so we load proper format
        usingS3 = (
                settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")

        # THe precise field with the valid filename / path depends on the storage adapter, so handle accordingly
        if usingS3:
            filename = data_model.data_file.name

        else:
            filename = data_model.data_file.path

        # Load the file object from Django storage backend, save it to local /tmp dir
        data_file_bytes = default_storage.open(filename, mode='rb')
        print(f"File loaded from DB: {filename}")

        # look to see if there's anything in the data directory and, if so, zip and add to databse
        manifest = "No data..."

        with zipfile.ZipFile(data_file_bytes) as dataZipObj:

            for filename in dataZipObj.namelist():
                manifest = manifest + f"\n{filename}"

        data_model.zip_contents=f"DATA FILE MANIFEST:\n{manifest}"
        data_model.save()

    except Exception as e:
        logger.error(f"Error trying to calculate data file manifest for data file obj ID #{script_data_file_uuid}: {e}")


@celery_app.task(base=FaultTolerantTask, name="Zip script for export")
def createScriptExportZip(*args, script_id=-1, **kwargs):
    try:

        script = PythonScript.objects.get(id=pk)

        outputBytes = io.BytesIO()
        zipFile = ZipFile(outputBytes, mode='w', compression=zipfile.ZIP_DEFLATED)

        if script.data_file and script.data_file.data_file:

            try:
                # Check storage type so we load proper format
                usingS3 = (
                        settings.DEFAULT_FILE_STORAGE == "gremlin_gplv3.utils.storages.MediaRootS3Boto3Storage")

                # THe precise field with the valid filename / path depends on the storage adapter, so handle accordingly
                if usingS3:
                    filename = script.data_file.data_file.name

                else:
                    filename = script.data_file.data_file.path

                # Load the file object from Django storage backend, save it to local /tmp dir
                data_file_bytes = default_storage.open(filename, mode='rb')
                print(f"File loaded from DB: {filename}")

                serverZip = zipfile.ZipFile(data_file_bytes)

                print(f"Zip obj loaded from bytes {serverZip}")

                with tempfile.TemporaryDirectory() as tmpdirname:
                    print(f"Create {tmpdirname} to extract all to")
                    serverZip.extractall(tmpdirname)
                    print("Extract complete")

                    for root, _, filenames in os.walk(tmpdirname):
                        for root_name in filenames:
                            print(f"Handle zip of {root_name}")
                            name = os.path.join(root, root_name)
                            name = os.path.normpath(name)
                            with open(name, mode='rb') as extracted_file:
                                zipFile.writestr(f'/data/{root_name}', extracted_file.read())

                serverZip.close()

            except Exception as e:
                print(f"Error trying to export zip: {e}")

        # write the logs if they exist
        if script.setup_log:
            zipFile.writestr(f"/logs/setupLog.log", script.setup_log)
        if script.installer_log:
            zipFile.writestr(f"/logs/pipLog.log", script.installer_log)

        # write the config files if they exist
        config = {}
        if script.description:
            config['description'] = script.description
        else:
            config['description'] = "No description..."

        if script.supported_file_types:
            config['supported_file_types'] = script.supported_file_types
        else:
            config['supported_file_types'] = ""

        if script.env_variables:
            config['env_variables'] = script.env_variables
        else:
            config['env_variables'] = ""

        if script.schema:
            config['schema'] = script.schema
        else:
            config['schema'] = ""

        if script.name:
            config['name'] = script.name
        else:
            config['name'] = "NO NAME"

        config['type'] = script.type

        # if the config object is not empty... write to a config.json file
        if config is not {}:
            zipFile.writestr(f"/config.json", json.dumps(config))

        # write the list of python packages as a pip file
        if script.required_packages:
            zipFile.writestr(f"/setup/requirements.txt", script.required_packages)

        # write the setup script as a .sh file (probably not quite right)
        if script.setup_script:
            zipFile.writestr(f"/setup/install.sh", script.setup_script)

        # write the script as a package
        if script.script:
            zipFile.writestr(f"/script/script.py", script.script)
            zipFile.writestr(f"/script/__init__.py", "EXPORTED BY GREMLIN")

        # Close the zip archive
        zipFile.close()
        outputBytes.seek(io.SEEK_SET)

        filename = f"{script.name}-gremlin_export.zip"
        response = FileResponse(outputBytes, as_attachment=True, filename=filename)
        response['filename'] = filename
        return response

    except Exception as e:
        return Response(e,
                        status=status.HTTP_400_BAD_REQUEST)
