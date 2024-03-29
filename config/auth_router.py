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
from gremlin.users.api.views import RecoverUsernameViewSet, \
    NewPasswordRequestViewSet

# DRF Basics
urlpatterns = [
    url(r'RecoverUsername', RecoverUsernameViewSet.as_view()),
    url(r'ResetPassword', NewPasswordRequestViewSet.as_view())
]
