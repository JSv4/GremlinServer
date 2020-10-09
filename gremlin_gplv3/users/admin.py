from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.contrib.auth import get_user_model

from gremlin_gplv3.users.forms import UserChangeForm, UserCreationForm

User = get_user_model()


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):

    form = UserChangeForm
    add_form = UserCreationForm
    fieldsets = (("User", {"fields": ("name","role")}),) + auth_admin.UserAdmin.fieldsets
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('name', 'email', 'username', 'role', 'password1', 'password2',),
        }),
    )
    list_display = ["username", "role", "name", "is_superuser"]
    search_fields = ["name"]
