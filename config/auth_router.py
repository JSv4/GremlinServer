from django.conf.urls import url
from gremlin_gplv3.users.api.views import RecoverUsernameViewSet, \
    NewPasswordRequestViewSet

# DRF Basics
urlpatterns = [
    url(r'RecoverUsername', RecoverUsernameViewSet.as_view()),
    url(r'ResetPassword', NewPasswordRequestViewSet.as_view())
]
