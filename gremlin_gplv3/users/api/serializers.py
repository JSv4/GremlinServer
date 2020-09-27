from rest_framework import serializers

from gremlin_gplv3.users.models import User


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "name", "url", "role"]

        extra_kwargs = {
            "url": {"view_name": "api:user-detail", "lookup_field": "username"}
        }


class SimpleUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "name", "role"]
