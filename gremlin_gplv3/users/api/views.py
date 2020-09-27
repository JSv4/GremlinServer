import secrets
from django.contrib.auth import get_user_model
from django.http import JsonResponse
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework.permissions import BasePermission
from rest_framework.permissions import IsAuthenticated
from ..paginations import MediumResultsSetPagination
from ..InvitationEmails import SendInviteEmail

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

class ResetPasswordViewSet(APIView):

    allowed_methods = ['post']
    permission_classes = [IsAuthenticated]

    def post(self, request, format=None):

        try:



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
