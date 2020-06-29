from django.conf import settings
from django.conf.urls import url
from rest_framework.routers import DefaultRouter
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from rest_framework import permissions

from gremlin_gplv3.users.api.views import UserViewSet
from Jobs.views import JobViewSet, DocumentViewSet, ResultsViewSet, \
    PipelineViewSet, PythonScriptViewSet, PipelineStepViewSet, LogViewSet, \
    UploadScriptViewSet, ProjectViewSet

schema_view = get_schema_view(
   openapi.Info(
      title="Gremlin API",
      default_version='v1',
      description="The open source, legaltech microservices framework.",
      terms_of_service="No warranties of any sort, express of implied and provided solely as-is and at your risk. More detail to come.",
      contact=openapi.Contact(email="john@thelegal.engineer"),
      license=openapi.License(name="GPLv3"),
   ),
   public=True,
   permission_classes=(permissions.IsAuthenticated,),
)

# DRF Basics
router = DefaultRouter()
router.register(r'Users', UserViewSet)
router.register(r'Jobs', JobViewSet)
router.register(r'Documents', DocumentViewSet)
router.register(r'Results', ResultsViewSet)
router.register(r'PipelineSteps', PipelineStepViewSet)
router.register(r'PythonScripts', PythonScriptViewSet)
router.register(r'Pipelines', PipelineViewSet)
router.register(r'Logs', LogViewSet)

app_name = "api"

urlpatterns = [
    *router.urls,
    url(r'CreateAndLaunchJob', ProjectViewSet.as_view()),
    url(r'UploadScript', UploadScriptViewSet.as_view()),
    url(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    url(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    url(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    ]
