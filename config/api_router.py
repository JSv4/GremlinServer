from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from Jobs.views import AllJobViewSet, PaginatedJobViewSet, DocumentViewSet, ResultsViewSet, \
    PipelineViewSet, PythonScriptViewSet, PipelineStepViewSet, LogViewSet, \
    UploadScriptViewSet, ProjectViewSet, EdgeViewSet, UploadPipelineViewSet, \
    DashboardAggregatesViewSet

from gremlin_gplv3.users.api.views import InviteUserViewSet, AllUserViewSet, \
    UserViewSet, ChangePasswordViewSet

# DRF Basics
router = DefaultRouter()
router.register(r'User', UserViewSet)
router.register(r'Users', AllUserViewSet)
router.register(r'Jobs', PaginatedJobViewSet)
router.register(r'AllJobs', AllJobViewSet)
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
    url(r'UploadScript', UploadScriptViewSet.as_view()),
    url(r'UploadPipeline', UploadPipelineViewSet.as_view()),
    url(r'InviteUser', InviteUserViewSet.as_view()),
    url(r'ChangePassword', ChangePasswordViewSet.as_view()),
    url(r'SystemStats', DashboardAggregatesViewSet.as_view())
]

