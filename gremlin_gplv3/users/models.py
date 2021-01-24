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

from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, EmailField
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class GremlinUserManager(BaseUserManager):

    def create_user(self, email, username, password, alias=None):
        if not email:
            raise ValueError("Must provide an e-mail")
        if not username:
            raise ValueError("Must provide a username")
        if not password:
            raise ValueError("Please provide a password")
        if not alias:
            alias = username

        user = self.model(
            email=self.normalize_email(email),
            username=username)
        user.set_password(password)
        user.save()

        return user

    def create_superuser(self, email, username, password, alias=None):

        user = self.create_user(email, username, password, alias=alias)
        user.is_staff = True
        user.is_superuser = True
        user.role = User.ADMIN # Making sure an admin role is defined by default for super user
        user.save()

        return user


class User(AbstractUser):

    # User Roles (very basic for now)
    LAWYER = "LAWYER"
    LEGAL_ENG = 'LEGAL_ENG'
    ADMIN = 'ADMIN'
    VIEWONLY = 'VIEWONLY'

    USER_ROLE = [
        (VIEWONLY, _('View Only')),
        (LAWYER, _('Lawyer')),
        (LEGAL_ENG, _('Legal Engineer')),
        (ADMIN, _('All Privileges (Dangerous!)')),
    ]

    # First Name and Last Name do not cover name patterns
    # around the globe.
    name = CharField(_("Name of User"), blank=True, max_length=255)

    # Override e-mail field so that it is required and unique
    email = EmailField(_('email address'), blank=False, unique=True)

    # User role
    role = CharField(
        max_length=24,
        blank=False,
        null=False,
        choices=USER_ROLE,
        default=LAWYER,
    )

    # Some tips on how to setup postgres indexing: http://rubyjacket.com/build/django-psql-fts.html
    email_vector = SearchVectorField(null=True)
    name_vector = SearchVectorField(null=True)
    username_vector = SearchVectorField(null=True)

    objects = GremlinUserManager()

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})

    class Meta:
        indexes = [GinIndex(fields=[
            'email_vector',
            'name_vector',
            'username_vector',
        ])]
