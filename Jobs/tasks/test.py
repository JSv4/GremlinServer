# Required Imports #####################################################################################################

# e.g. from OCRUSREX import ocrusrex

# Don't forget that, if these imports are not already available, you'll need to list them out in the
# required dependencies so that Gremlin can install them in the environment.

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
    print("Should see me in console.")

    # Clustering-related imports

    # General imports
    import re

    # Data Science Imports

    # NLP Job Libraries
    import nltk
    import spacy
    from nltk.stem.snowball import SnowballStemmer

    print("Imports done.")
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

    returnObj = {
        "allwords_stemmed": allwords_stemmed,
        "allwords_tokenized": allwords_tokenized,
        "raw_text": docText
    }

    return True, "Successfully extracted TFIDF features!", returnObj, None, None
