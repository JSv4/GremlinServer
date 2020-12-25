from __future__ import absolute_import, unicode_literals

import logging, zipfile, io, tempfile, os, celery, json, base64

from django.core.files.base import ContentFile
from django.db import connection
from config import celery_app
from celery import chain, group, chord
from django.conf import settings
from django.core.files.storage import default_storage
from datetime import datetime

from Jobs.tasks.task_helpers import FaultTolerantTask
from Jobs.models import ScriptDataFile, PythonScript, UserNotification

# Excellent django logging guidance here: https://docs.python.org/3/howto/logging-cookbook.html
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

########################################################################################################################
##                                                                                                                    ##
##                              Built-in scripts to perform long-running platform tasks                               ##
##                                                                                                                    ##
########################################################################################################################

class FaultTolerantTask(celery.Task):
    """ Implements after return hook to close the invalid connection.
    This way, django is forced to serve a new connection for the next
    task.
    """
    abstract = True

    def after_return(self, *args, **kwargs):
        connection.close()


# Task to import a data file zip - note, there is duplicate, SYNCHRONOUS logic in the view to for the upload_data action
# in the ScriptViewSet. For now, performance seems acceptable with uploads not having to wait for the data file to upload
# and get moved to storage BUT... if that becomes a problem, would probably be appropriate to find a way to use this there
# to and indicate on the backend somewhere that the data file is "processing". For now, just used as part of chain of tasks
# used for a pipeline import from ZIP.
@celery_app.task(base=FaultTolerantTask, name='Upload pipeline zip file')
def loadDataFilesFromZipBytes(*args, ascii_zip_bytes_string=None, **kwargs):

    return_data = {'error': None}
    data_file_lookup = {}

    try:

        data_bytes = base64.b64decode(ascii_zip_bytes_string)
        import_bytes = io.BytesIO(data_bytes)
        import_zip = zipfile.ZipFile(import_bytes)

        # Format should have all needed data files in a /data directory as zip files... so only look at these files
        for filename in [name for name in import_zip.namelist() if name.startswith('/data/') and name.endswith(".zip")]:

            old_uuid = filename[6:-4]  # Since we know data zips are in /data/, end in zip and in between is old uuid...
            data_file_bytes = io.BytesIO(import_zip.open(filename).read())
            manifest = ""

            with zipfile.ZipFile(data_file_bytes) as dataZipObj:

                for data_filename in dataZipObj.namelist():

                    manifest = manifest + f"\n{data_filename}" if manifest else data_filename

            # Create Django ContentFile to upload to ScriptDataFile obj
            data_zip_file = ContentFile(data_file_bytes.getvalue())

            # Create new ScriptDataFile obj
            db_data_obj = ScriptDataFile.objects.create()

            # Update new ScriptDataFile obj with
            db_data_obj.manifest = manifest
            db_data_obj.data_file.save("data.zip", data_zip_file)
            db_data_obj.save()

            # Now map the imported ScriptDataFile obj old UUID to the one on THIS system
            data_file_lookup[old_uuid] = f"{db_data_obj.uuid}"

        import_zip.close()

        print("Finished importing data from zip")

        return_data['data_file_lookup'] = data_file_lookup

    except Exception as e:
        error = f"Unable to import scrip data files for pipeline import. ERROR: {e}"
        print(error)
        return_data['error'] = error

    return return_data


# Task to calculate list of files in a zip.
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
        manifest = ""

        with zipfile.ZipFile(data_file_bytes) as dataZipObj:

            for filename in dataZipObj.namelist():
                manifest = manifest + f"\n{filename}" if manifest else filename

        data_model.manifest= f"DATA FILE MANIFEST:\n{manifest}"
        data_model.save()

    except Exception as e:
        logger.error(f"Error trying to calculate data file manifest for data file obj ID #{script_data_file_uuid}: {e}")


# Task to zip up a script and store it in the DB. This is currently not used. Performance has been okay doing this
# within the views... Rather than recode import/export using celery tasks - which will require an entirely new messaging
# system on the frontend... let's see how the performance is doing this in the views for now... I suspect it will probably
# be OK for most data but will cause issues for files that are over a couple hundred MBs. I do think this needs to be
# addressed eventually BUT probably not a great use of time right now.
@celery_app.task(base=FaultTolerantTask, name="Zip script for export")
def createScriptExportZip(*args, script_id=-1, owner_id=-1, **kwargs):

    try:

        script = PythonScript.objects.get(id=script_id)

        outputBytes = io.BytesIO()
        zipFile = zipfile.ZipFile(outputBytes, mode='w', compression=zipfile.ZIP_DEFLATED)

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

        notification = UserNotification.objects.create(
            type=UserNotification.SCRIPT_EXPORT,
            owner_id=owner_id,
            message="Your script export has completed successfully!",
        )

        notification.data_file.save(ContentFile(outputBytes))

    except Exception as e:
        logger.error(f"Error zipping script: {script_id}")