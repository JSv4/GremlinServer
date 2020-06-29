import logging

db_default_formatter = logging.Formatter()

def addTaskLog(resultId=-1, msg="", loggerName="Task"):

	from .models import TaskLogEntry, Result

	try:
		kwargs = {
			'logger_name': loggerName,
			'level': "INFO",
			'msg': msg,
			'result': Result.objects.get(id=resultId)
		}
		TaskLogEntry.objects.create(**kwargs)
	except:
		logging.error(f"Error on addTaskLog for result {resultId} with message: {msg}")

def addJobLog(jobId=-1, msg="", loggerName="Job"):

	from .models import JobLogEntry, Job

	try:
		kwargs = {
			'logger_name': loggerName,
			'level': "INFO",
			'msg': msg,
			'result': Job.objects.get(id=jobId)
		}
		JobLogEntry.objects.create(**kwargs)

	except:
		logging.error(f"Error on addJobLog for job {jobId} with message: {msg}")


class TaskDatabaseLogHandler(logging.Handler):
	def emit(self, record, **kwargs):

		if hasattr(record, "resultId"):

			from .models import TaskLogEntry, Result

			trace = None

			if record.exc_info:
				trace = db_default_formatter.formatException(record.exc_info)

			try:
				msg = self.format(record)
			except Exception as e:
				msg = record.getMessage()

			kwargs = {
				'logger_name': record.name,
				'level': record.levelno,
				'msg': msg,
				'trace': trace,
				'result': Result.objects.get(id=record.resultId)
			}

			TaskLogEntry.objects.create(**kwargs)

	def format(self, record):
		if self.formatter:
			fmt = self.formatter
		else:
			fmt = db_default_formatter

		if type(fmt) == logging.Formatter:
			record.message = record.getMessage()

			if fmt.usesTime():
				record.asctime = fmt.formatTime(record, fmt.datefmt)

			# ignore exception traceback and stack info

			return fmt.formatMessage(record)
		else:
			return fmt.format(record)

class JobDatabaseLogHandler(logging.Handler):
	def emit(self, record, **kwargs):

		if hasattr(record, "jobId"):

			from .models import JobLogEntry, Job

			trace = None

			if record.exc_info:
				trace = db_default_formatter.formatException(record.exc_info)

			try:
				msg = self.format(record)
			except Exception as e:
				msg = record.getMessage()

			kwargs = {
				'logger_name': record.name,
				'level': record.levelno,
				'msg': msg,
				'trace': trace,
				'job': Job.objects.get(id=record.jobId)
			}

			JobLogEntry.objects.create(**kwargs)

	def format(self, record):
		if self.formatter:
			fmt = self.formatter
		else:
			fmt = db_default_formatter

		if type(fmt) == logging.Formatter:
			record.message = record.getMessage()

			if fmt.usesTime():
				record.asctime = fmt.formatTime(record, fmt.datefmt)

			# ignore exception traceback and stack info

			return fmt.formatMessage(record)
		else:
			return fmt.format(record)
