from django.contrib import admin

from .models import Document, Job, Result, PythonScript, Pipeline, PipelineNode, \
	TaskLogEntry, JobLogEntry, Edge, ScriptDataFile

@admin.register(ScriptDataFile)
class DataFileAdmin(admin.ModelAdmin):
	list_display = ['creation_time', 'modified', 'pk']

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
	list_display = ['name', 'extracted']
	search_fields = ['name',]

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
	list_display = ['name', 'start_time','stop_time']
	search_fields = ['name']

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
	list_display = ['name','queued','started', 'error', 'finished','status', 'creation_time']
	search_fields = ['name']

@admin.register(PipelineNode)
class PipelineStepAdmin(admin.ModelAdmin):
	list_display = ['name','script']
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
	list_display = ['name', 'description']
	search_fields = ['name']

