#OCR Job Libraries #####################################################################################################
from OCRUSREX import ocrusrex
########################################################################################################################

def pythonFunction(*args, docType="", docText="", docName="", docByteObj=None,
                   scriptInputs={}, previousData={}, logger=None, **kwargs):
    
	ocredPdf = ocrusrex.Multithreaded_OCRPDF(source=docByteObj, verbose=True)

	logger.info("Doc OCRed Successfully: ".format(docName))

	return (True, "Successfully OCRed: {0}!".format(docName), {"Doc":docName}, ocredPdf, "pdf")