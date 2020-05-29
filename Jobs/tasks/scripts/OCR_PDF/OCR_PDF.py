#OCR Job Libraries #####################################################################################################
from OCRUSREX import ocrusrex
########################################################################################################################

def pythonFunction(*args, docType="", docText="", docName="", docByteObj=None,
                   scriptInputs={}, previousData={}, logger=None, **kwargs):
    
	
	print(type(docByteObj))
	
	ocredPdf = ocrusrex.Multithreaded_OCRPDF(source=docByteObj, verbose=True, tesseract_config = '--oem 1 --psm 6 -c preserve_interword_spaces=1')

	logger.info("Doc OCRed Successfully: ".format(docName))

	return (True, "Successfully OCRed: {0}!".format(docName), {"Doc":docName}, ocredPdf, "pdf")