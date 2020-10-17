# Errors
class Error(Exception):
    """Base class for exceptions in this module."""
    pass


class FileNotSupportedError(Error):
    """Exception raised for unsupported file input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message


class FileInputError(Error):
    """Exception raised for errors in the file input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


class DataInputError(Error):
    """Exception raised for errors in the data input.

    Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


class UserScriptError(Error):
    """Raised when User's script fails.

   Attributes:
        expression -- input expression in which the error occurred
        message -- explanation of the error
    """

    def __init__(self, expression, message):
        self.expression = expression
        self.message = message


class PrecedingNodeError(Error):
    """Raised when previous step in a pipeline fails.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message


class JobAlreadyFinishedError(Error):
    """Raised when somehow node is running but job is done. Not sure this can actually happen unless DB corrupted.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message


class UserScriptError(Error):
    """Raised when user script fails.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message


class PipelineError(Error):
    """Raised when user script fails.

   Attributes:
        message -- explanation of the error
    """

    def __init__(self, message):
        self.message = message
