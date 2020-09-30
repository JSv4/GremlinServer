import secrets
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework.permissions import IsAuthenticated, BasePermission, AllowAny
from ..paginations import MediumResultsSetPagination
from ..InvitationEmails import SendInviteEmail, SendResetPasswordEmail, SendUsernameEmail

from .serializers import UserSerializer, SimpleUserSerializer

User = get_user_model()

# Write-Only Permissions on Script, Pipeline and PipelineStep for users with
# role = LAWYER
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

        except Exception as e:
            print("Exception encountered: ")
            print(e)
            return Response(e,
                            status=status.HTTP_400_BAD_REQUEST)
