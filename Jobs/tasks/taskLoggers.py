import logging

db_default_formatter = logging.Formatter()

def addTaskLog(resultId=-1, msg="", loggerName="Task", level="INFO"):

	from ..models import TaskLogEntry, Result

	try:
		kwargs = {
			'logger_name': loggerName,
			'level': level,
			'msg': msg,
			'result': Result.objects.get(id=resultId)
		}
		TaskLogEntry.objects.create(**kwargs)

	except Exception as e:
		logging.error(f"Error adding message ({msg}) for result {resultId}: {e}")

class TaskLogger():

	def __init__(self, resultId, name=""):
		self.resultId = resultId
		self.name = name

	def info(self, msg):
		addTaskLog(resultId=self.resultId, msg=msg, loggerName=self.name, level=logging.INFO)

	def error(self, msg):
		addTaskLog(resultId=self.resultId, msg=msg, loggerName=self.name, level=logging.ERROR)

	def warn(self, msg):
		addTaskLog(resultId=self.resultId, msg=msg, loggerName=self.name, level=logging.WARN)

def addJobLog(jobId=-1, msg="", loggerName="Job", level="INFO"):

	from ..models import JobLogEntry, Job

	try:
		kwargs = {
			'logger_name': loggerName,
			'level': level,
			'msg': msg,
			'job': Job.objects.get(id=jobId)
		}
		JobLogEntry.objects.create(**kwargs)

	except Exception as e:
		logging.error(f"Error adding message ({msg}) for job {jobId}: {e}")


class JobLogger():

	def __init__(self, jobId, name=""):
		self.jobId = jobId
		self.name = name

	def info(self, msg):
		addJobLog(jobId=self.jobId, msg=msg, loggerName=self.name, level=logging.INFO)

	def error(self, msg):
		addJobLog(jobId=self.jobId, msg=msg, loggerName=self.name, level=logging.ERROR)

	def warn(self, msg):
		addJobLog(jobId=self.jobId, msg=msg, loggerName=self.name, level=logging.WARN)
