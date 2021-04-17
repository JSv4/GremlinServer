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

import secrets

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import JsonResponse
from django_filters import rest_framework as filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework.permissions import IsAuthenticated, BasePermission, AllowAny

from gremlin.utils.filters import UserFilter
from ..paginations import MediumResultsSetPagination
from gremlin.utils.emails import SendInviteEmail, SendResetPasswordEmail, SendUsernameEmail
from gremlin.users.models import User as CustomUser

from .serializers import UserSerializer, SimpleUserSerializer

User = get_user_model()

# Permission class only gives access to admin or legal engineers
class AdminAccessOnly(BasePermission):

    """
    Allows access only to "ADMIN" users.
    """
    def has_permission(self, request, view):
        return request.user.role == "ADMIN"


class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):

    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "username"
    pagination_class = MediumResultsSetPagination
    permission_classes = [IsAuthenticated]

    def get_queryset(self, *args, **kwargs):
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False, methods=["GET"])
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)

class AllUserViewSet(ModelViewSet):

    serializer_class = SimpleUserSerializer
    queryset = User.objects.all()
    pagination_class = MediumResultsSetPagination
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = UserFilter
    permission_classes = [AdminAccessOnly]

    # Override certain viewset actions to disable them
    # https://www.django-rest-framework.org/api-guide/viewsets/#viewset-actions
    # https://stackoverflow.com/a/60335729/2938099

    def create(self, request):
        response = {'message': 'Create function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)

    def update(self, request, pk=None):
        response = {'message': 'Update function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)

    def partial_update(self, request, pk=None):
        response = {'message': 'Update function is not offered in this path.'}
        return Response(response, status=status.HTTP_403_FORBIDDEN)

    # lets admin users elevate or demote other users.
    @action(detail=True, methods=["PUT"])
    def change_permissions(self, request, pk=None):
        try:
            user = User.objects.get(pk=pk)
            new_role = request.data['role']
            if new_role in [item[0] for item in CustomUser.USER_ROLE]:
                if user.role==CustomUser.ADMIN:
                    message = "ERROR - You cannot demote admins through this interface. " \
                              "Use the Gremlin backend admin panel."
                else:
                    user.role = new_role
                    user.save()
                    return JsonResponse(self.get_serializer(user).data, status=status.HTTP_200_OK)
            else:
                message = f"ERROR - Role must be one of {CustomUser.USER_ROLE}"

            return Response(message, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response(f"Error: {e}", status=status.HTTP_500_INTERNAL_SERVER_ERROR,)

class NewPasswordRequestViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [AllowAny]

    def post(self, request):

        try:

            matching_users = User.objects.filter(username=request.data['username'])

            if matching_users.count() == 1:
                user = matching_users[0]
                print(f"I recognize this user. Create a new password and email it to: {user.email}")

                password = secrets.token_urlsafe(16)
                print(f"Password is: {password}")

                # Try to send the email first AND only if it succeeds, change the password (because this
                # is the ONLY time / place you can retrieve the new password and if it doesn't get e-mailed
                # you've locked the user out. You can always just send another password request too...
                if SendResetPasswordEmail(user.username, user.name, password, user.email):
                    user.set_password(password)
                    user.save()
                    return Response("Success", status=status.HTTP_200_OK)
                else:
                    return Response("Unable to send password recovery email... NOT changing password.",
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            else:
                return Response("This is not a valid username.",
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            print("Something went wrong trying to reset password.")
            print(e)
            return Response(e,
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class RecoverUsernameViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [AllowAny]

    def post(self, request, format=None):

        try:

            matching_users = User.objects.filter(email=request.data['email'])

            if matching_users.count() == 1:

                user = matching_users[0]

                if SendUsernameEmail(user.username, user.name, user.email):
                    return Response("Success sending username reminder email",
                                    status=status.HTTP_200_OK)
                else:
                    return Response("Error sending username reminder email.",
                                    status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            else:
                return Response("This is not a valid e-mail.",
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            print("Something went wrong trying to recover username.")
            print(e)
            return Response(e,
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class ChangePasswordViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [IsAuthenticated]

    def post(self, request):

        try:
            if request.user.check_password(request.data['old_password']):
                request.user.set_password(request.data['new_password'])
                request.user.save()
                return Response("Successfully changed password",
                                status=status.HTTP_204_NO_CONTENT)
            else:
                return Response("Old Password Is Invalid",
                                status=status.HTTP_200_OK)

        except Exception as e:
            print("Exception encountered: ")
            print(e)
            return Response(e,
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class UpdatePasswordViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):

        try:

            print(f"Old password: {request.data['old_password']}")
            print(f"New password: {request.data['new_password']}")

            if self.user.check_password(request.data['old_password']):
                request.user.set_password('new password')
            else:
                return Response("Old Password Is Invalid",
                                status=status.HTTP_200_OK)

        except Exception as e:
            print("Exception encountered: ")
            print(e)
            return Response(e,
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class InviteUserViewSet(APIView):

    allowed_methods = ['put']
    permission_classes = [AdminAccessOnly]
    ordering = ['id']

    def put(self, request, format=None):

        print("Try PUT:")

        try:
            serializer = SimpleUserSerializer(request.data)
            print("Got new user request:")
            print(request.data)
            print(serializer.data)

            password = secrets.token_urlsafe(16)

            newUser = User.objects.create_user(
                **serializer.data,
                password=password)

            SendInviteEmail(
                serializer.data['username'],
                serializer.data['name'],
                password,
                serializer.data['email'])

            response = JsonResponse(SimpleUserSerializer(newUser).data)

            return response

        except IntegrityError as e:
            return JsonResponse({'message': e.args[0]},
                            status=status.HTTP_409_CONFLICT)

        except Exception as ge:
            return JsonResponse({'message': ge.__cause__},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
