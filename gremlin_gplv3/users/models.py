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
