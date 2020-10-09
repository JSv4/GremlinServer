from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.contrib.auth.models import AbstractUser
from django.db.models import CharField, EmailField
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _


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

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})

    class Meta:
        indexes = [GinIndex(fields=[
            'email_vector',
            'name_vector',
            'username_vector',
        ])]
