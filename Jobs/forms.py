from django.contrib.postgres import forms

# Needed to override the default JSONField due to some undesired validation behavior where an empty dict throws a
# validation error for JSONField.
# See: https://stackoverflow.com/questions/55147169/django-admin-jsonfield-default-empty-dict-wont-save-in-admin
class MyJSONField(forms.JSONField):
    empty_values = [None, "", [], ()]