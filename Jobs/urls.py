# gremlin URL Configuration
# Note, I am seeing a sporadic deadlock error "deadlock detected by _ModuleLock(django.test.signals) on startup
# According to this SO post (https://stackoverflow.com/questions/55844680/deadlock-detected-when-trying-to-start-server)
# This may be due to DRF. Some suggestions were related to urls.py though my version doesn't seem to benefit from
# the guidance therein.

from rest_framework import routers
from django.urls import path, include
from . import views

router = routers.DefaultRouter()
router.register(r'Jobs', views.JobViewSet)
router.register(r'Documents', views.DocumentViewSet)
router.register(r'Results', views.ResultsViewSet)
router.register(r'FileResults', views.FileResultsViewSet)
router.register(r'PipelineSteps',views.PipelineStepViewSet)
router.register(r'PythonScripts', views.PythonScriptViewSet)
router.register(r'Pipelines', views.PipelineViewSet)
router.register(r'Logs', views.LogViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
