# Required Imports #####################################################################################################

# e.g. from OCRUSREX import ocrusrex

# Don't forget that, if these imports are not already available, you'll need to list them out in the
# required dependencies so that Gremlin can install them in the environment.

########################################################################################################################

# user-defined functions to run on docs should expect the following inputs:
#
# docText = extracted document text
# docType = file extension
# docName = file name
# docByteObj = actual document binary in bytes
# logger = Gremlin database logger (resuts will are available via API)
# scriptInputs = inputs for this script (NOT IMPLEMENTED. Will be NONE)
# previousData = the combined output data from the previous step. If previous step was run in parallel on all docs, results are packed up into one json.
#
# the logger object will be a special instance of the logger just for user scripts and
# will write out messages to the Gremlin UI (not implemented yet). Currently these
# are stored in the underlying Celery logs.
def pythonFunction(*args, docText=None, docType=None, docName=None, docByteObj=None, logger=None, scriptInputs=None,
				   previousData=None, **kwargs):
	
	import sys
	logger.info("Available packages in Spacy env\n")
	logger.info(sys.modules.keys())
	
	# Programmatically get list of available packages https://stackoverflow.com/questions/35120646/python-programmatically-running-pip-list
	from pkgutil import iter_modules
	logger.info("What packages are available on system?\n")
	logger.info([p.name for p in iter_modules()])
	
	# Get files
	from os import listdir
	from os.path import isfile, join
	onlyfiles = [f for f in listdir("/tmp") if isfile(join("/tmp", f))]
	logger.info(f"Here's the contents of /tmp: \n{onlyfiles}")
		
	logger.info("Mark One")

	try:
		
		# utilities and django
		# libraries##########################################################################################
		import io
		import os
		from zipfile import ZipFile

		# NLP Job Libraries #####################################################################################################
		from spacy import displacy
		import spacy
		########################################################################################################################
		resultObj = io.BytesIO()
		
		print("Load Stuff")
		# initialize Spacy and perform analysis:
		from spacy.lang.en import English
		nlp = English()
		#nlp = spacy.load('en_core_web_lg')
		logger.info("Spacy loaded. Woooo booooy")
		logger.info(type(docText))
		logger.info("docText")
		logger.info(docText)
		analyzedDoc = nlp(docText)
		logger.info("Document analyzed.")
		nents = dict([(str(x), x.label_) for x in analyzedDoc.ents])
		logger.info("Entities extracted.")
		orgMatches = dict(filter(lambda item: item[1] == "ORG", nents.items()))
		html = displacy.render(analyzedDoc, style="ent", page=True)
		logger.info("HTML prepared.")
	
		# Create zipfile contents:
		baseFilename = os.path.basename(docName)
		htmlFilename = str.split(baseFilename, "-ANALYSIS.")[0] + ".html"
		txtFilename = str.split(baseFilename, "-TEXT.")[0] + ".txt"
	
		# write out to results file obj
		docResults = ZipFile(resultObj, 'w')
		docResults.writestr(txtFilename, docText)  # write plaintext extract to batch results zip
		docResults.writestr(htmlFilename, html)  # write original file to batch results zip
		docResults.close()
	
		print("Doc ID Processed Successfully!"
		return (True, "Successfully extracted named entities!", orgMatches, resultObj.getvalue(), ".zip")
	
	except Exception as e:
		logger.info("Error encountered: ")
		logger.error(e)
		jobLogger.error(traceback.print_exc())
		return (False, f"{e}", {}, None, None)