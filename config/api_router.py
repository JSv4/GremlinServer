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

from django.conf.urls import url
from rest_framework.routers import DefaultRouter

from gremlin.jobs.views import JobViewSet, DocumentViewSet, ResultsViewSet, \
    PipelineViewSet, PythonScriptViewSet, PipelineStepViewSet, LogViewSet, \
    UploadScriptViewSet, ProjectViewSet, EdgeViewSet, \
    DashboardAggregatesViewSet, ScriptDataFileViewset, UploadPipelineZipViewSet

from gremlin.users.api.views import InviteUserViewSet, AllUserViewSet, \
    UserViewSet, ChangePasswordViewSet

# DRF Basics
router = DefaultRouter()
router.register(r'User', UserViewSet)
router.register(r'Users', AllUserViewSet)
router.register(r'Jobs', JobViewSet)
router.register(r'Documents', DocumentViewSet)
router.register(r'Results', ResultsViewSet)
router.register(r'PipelineSteps', PipelineStepViewSet)
router.register(r'PipelineEdges', EdgeViewSet)
router.register(r'PythonScripts', PythonScriptViewSet)
router.register(f'DataFiles', ScriptDataFileViewset)
router.register(r'Pipelines', PipelineViewSet)
router.register(r'Logs', LogViewSet)

app_name = "api"

urlpatterns = [
    *router.urls,
    url(r'CreateAndLaunchJob', ProjectViewSet.as_view()),
    url(r'UploadScript', UploadScriptViewSet.as_view()),
    # url(r'UploadPipeline', UploadPipelineViewSet.as_view()),
    url(r'UploadPipelineZip', UploadPipelineZipViewSet.as_view()),
    url(r'InviteUser', InviteUserViewSet.as_view()),
    url(r'ChangePassword', ChangePasswordViewSet.as_view()),
    url(r'SystemStats', DashboardAggregatesViewSet.as_view())
]

