"""
Gremlin - The open source legal engineering platform
Copyright (C) 2020-2021 John Scrudato IV ("JSIV")

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/
"""

import logging

db_default_formatter = logging.Formatter()

def addTaskLog(resultId=-1, msg="", loggerName="Task"):

	from .models import TaskLogEntry, Result

	try:
		kwargs = {
			'logger_name': loggerName,
			'level': "INFO",
			'msg': msg,
			'result': Result.objects.get(id=resultId),
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
			'result': Job.objects.get(id=jobId),
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
				'result': Result.objects.get(id=record.resultId),
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
			from gremlin_gplv3.users.models import User

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
				'job': Job.objects.get(id=record.jobId),
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
