from django.conf import settings
from django.conf.urls import url
from rest_framework.routers import DefaultRouter
from rest_framework.documentation import include_docs_urls

from gremlin_gplv3.users.api.views import UserViewSet
from Jobs.views import JobViewSet, DocumentViewSet, ResultsViewSet, \
    PipelineViewSet, PythonScriptViewSet, PipelineStepViewSet, LogViewSet, \
    UploadScriptViewSet, ProjectViewSet, EdgeViewSet

# DRF Basics
router = DefaultRouter()
router.register(r'Users', UserViewSet)
router.register(r'Jobs', JobViewSet)
router.register(r'Documents', DocumentViewSet)
router.register(r'Results', ResultsViewSet)
router.register(r'PipelineSteps', PipelineStepViewSet)
router.register(r'PipelineEdges', EdgeViewSet)
router.register(r'PythonScripts', PythonScriptViewSet)
router.register(r'Pipelines', PipelineViewSet)
router.register(r'Logs', LogViewSet)

app_name = "api"

urlpatterns = [
    *router.urls,
    url(r'CreateAndLaunchJob', ProjectViewSet.as_view()),
    url(r'UploadScript', UploadScriptViewSet.as_view())
]

