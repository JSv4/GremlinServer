#Required Imports #####################################################################################################

#e.g. from OCRUSREX import ocrusrex

    #Don't forget that, if these imports are not already available, you'll need to list them out in the
    #required dependencies so that Gremlin can install them in the environment. 

########################################################################################################################

# user-defined functions to run on docs should expect the following, read-only objects:
# job
# doc
# step
#
# the logger object will be a special instance of the logger just for user scripts and 
# will write out messages to the Gremlin UI (not implemented yet). Currently these
# are stored in the underlying Celery logs.
def pythonFunction(*args, docText=None, docType=None, docName=None, 
docByteObj=None, logger=None, scriptInputs=None, previousData=None, 
**kwargs):
    
    logger.info("Load Imports for TFIDF")

    # Clustering-related imports
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    from sklearn.metrics import silhouette_score

	# General imports
	import re
    import os
    import unicodedata
    import json
    from bs4 import BeautifulSoup

    # Data Science Imports
    import pandas as pd
	import numpy as np

    #NLP Job Libraries
    import nltk
    from spacy import displacy
    import spacy
    from nltk.stem.snowball import SnowballStemmer


    logger.info("TFIDF Extraction Started")

    # Define clustering util and processing functions
    def tokenize_and_stem(text):
        # first tokenize by sentence, then by word to ensure that punctuation is caught as it's own token
        tokens = [word for sent in nltk.sent_tokenize(text) for word in nltk.word_tokenize(sent)]
        filtered_tokens = []
        # filter out any tokens not containing letters (e.g., numeric tokens, raw punctuation)
        for token in tokens:
            if re.search('[a-zA-Z]', token):
                filtered_tokens.append(token)
        stems = [stemmer.stem(t) for t in filtered_tokens]
        return stems

    def tokenize_only(text):
        # first tokenize by sentence, then by word to ensure that punctuation is caught as it's own token
        tokens = [word.lower() for sent in nltk.sent_tokenize(text) for word in nltk.word_tokenize(sent)]
        filtered_tokens = []
        # filter out any tokens not containing letters (e.g., numeric tokens, raw punctuation)
        for token in tokens:
            if re.search('[a-zA-Z]', token):
                filtered_tokens.append(token)
        return filtered_tokens
    
    # Load up spacy with large training set
    nlp = spacy.load('en_core_web_lg')
    
    # Initialization of various key utils and objs
    stemmer = SnowballStemmer("english")

    logger.info("DOCUMENT SEMANTIC SIMILARITY CLUSTERING - Tokenize and stem raw text.")
    
    try:
        allwords_stemmed = tokenize_and_stem(docText)
        allwords_tokenized = tokenize_only(docText)
    except Exception as e:
        logger.error(
            "Error Tokenizing and Stemming: {0}".format(e))

    #return values - your function must return a tuple of the following form:
    #	( Completed, Message, Data, FileBytesObj, FileExtension)
    #		  |         |       |        |              |
    #	   Boolean    String  JSON    Bytes Obj       String
    #
    #   You must provided a value for Completed and Message. Everything else can
    #   Be returned as None or an empy object. If there is no data, return an 
    #   empty JSON {}. If there is no file to return return None for the FileBytesObj
    #   and None for the File Extension. Otherwise, return the BytesObj representing
    #   the file that should be stored, along with the file extension. File names
    #   are currently determined automatically, though that may change.  
    
    returnObj = {
        "allwords_stemmed": allwords_stemmed,
        "allwords_tokenized": allwords_tokenized,
        "raw_text": docText
    }

    return (True, "Successfully extracted TFIDF features!", returnObj, None, None)