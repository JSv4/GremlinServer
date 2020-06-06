from django.contrib.auth.models import AbstractUser
from django.db.models import CharField
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _


class User(AbstractUser):

    # User Roles (very basic for now)
    LAWYER = "LAWYER"
    LEGAL_ENG = 'LEGAL_ENG'
    ADMIN = 'ADMIN'

    USER_ROLE = [
        (LAWYER, _('Lawyer')),
        (LEGAL_ENG, _('Legal Engineer')),
        (ADMIN, _('All Privileges (Dangerous!)')),
    ]

    # First Name and Last Name do not cover name patterns
    # around the globe.
    name = CharField(_("Name of User"), blank=True, max_length=255)

    # User role
    role = CharField(
        max_length=24,
        blank=False,
        null=False,
        choices=USER_ROLE,
        default=LAWYER,
    )

    def get_absolute_url(self):
        return reverse("users:detail", kwargs={"username": self.username})
