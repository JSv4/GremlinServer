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

from django.contrib import admin

from .models import Document, Job, Result, PythonScript, Pipeline, PipelineNode, \
	TaskLogEntry, JobLogEntry, Edge, ScriptDataFile

@admin.register(ScriptDataFile)
class DataFileAdmin(admin.ModelAdmin):
	list_display = ['uuid', 'created', 'modified']

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ['id', 'name', 'extracted']
	search_fields = ['name',]

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
	list_display = ['id', 'name', 'start_time', 'stop_time']
	search_fields = ['name']

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
	list_display = ['id', 'name', 'queued', 'started', 'error', 'finished', 'status', 'created']
	search_fields = ['name']

@admin.register(PipelineNode)
class PipelineStepAdmin(admin.ModelAdmin):
	list_display = ['id', 'name', 'script']
	search_fields = ['name']

@admin.register(PythonScript)
class ScriptAdmin(admin.ModelAdmin):
	list_display = ['pk', 'human_name', 'type', 'description', 'mode']
	search_fields = ['human_name']

@admin.register(Edge)
class EdgeAdmin(admin.ModelAdmin):
    list_display = ['pk']

@admin.register(TaskLogEntry)
class TaskLogAdmin(admin.ModelAdmin):
	list_display =  ['level','logger_name']

@admin.register(JobLogEntry)
class JobLogAdmin(admin.ModelAdmin):
	list_display = ['level','logger_name','msg']

@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
	list_display = ['id', 'name', 'description']
	search_fields = ['name']

