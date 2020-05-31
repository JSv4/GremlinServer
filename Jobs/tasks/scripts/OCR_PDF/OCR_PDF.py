#OCR Job Libraries #####################################################################################################
from OCRUSREX import ocrusrex
########################################################################################################################

def pythonFunction(*args, docType="", docText="", docName="", docByteObj=None,
                   scriptInputs={}, previousData={}, logger=None, **kwargs):
    
	
	import os, pwd
	from os import listdir
	from os.path import isfile, join
	
	logger.info(f"My user is: {pwd.getpwuid(os.getuid()).pw_name}")

	logger.info("pythonFunction TESSDATA_PREFIX:")
	logger.info(os.getenv('TESSDATA_PREFIX'))
	
	mypath="/usr/local/share/tessdata"
	
	onlyfiles = [f for f in listdir(mypath) if isfile(join(mypath, f))]
	logger.info("Files in /usr/local/share/tessdata:")
	logger.info(onlyfiles)
	
	#ocredPdf = ocrusrex.Multithreaded_OCRPDF(source=docByteObj, verbose=True, tesseract_config = '--oem 1 --psm 6 -c preserve_interword_spaces=1')
	ocredPdf = ocrusrex.OCRPDF(source=docByteObj, verbose=True, tesseract_config='--oem 1 --psm 6 -l eng -c preserve_interword_spaces=1')

	logger.info("Doc OCRed Successfully: ".format(docName))

	return (True, "Successfully OCRed: {0}!".format(docName), {"Doc":docName}, ocredPdf, "pdf")