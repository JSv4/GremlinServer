from django.conf import settings
from django.conf.urls import url
from rest_framework.routers import DefaultRouter, SimpleRouter

from gremlin_gplv3.users.api.views import UserViewSet
from Jobs.views import JobViewSet, DocumentViewSet, ResultsViewSet, \
    PipelineViewSet, PythonScriptViewSet, PipelineStepViewSet, LogViewSet, \
    UploadScriptViewSet

# if settings.DEBUG:
#     router = DefaultRouter()
# else:
#     router = SimpleRouter(

router=DefaultRouter()

router.register("users", UserViewSet)
router.register(r'Jobs', JobViewSet)
router.register(r'Documents', DocumentViewSet)
router.register(r'Results', ResultsViewSet)
router.register(r'PipelineSteps', PipelineStepViewSet)
router.register(r'PythonScripts', PythonScriptViewSet)
# router.register(r'UploadScript', UploadScriptViewSet.as_view())
router.register(r'Pipelines', PipelineViewSet)
router.register(r'Logs', LogViewSet)

app_name = "api"
urlpatterns = [
                *router.urls,
                url(r'UploadScript', UploadScriptViewSet.as_view())
               ]
