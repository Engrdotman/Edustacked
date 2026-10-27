"""Email login backend for accounts with an unambiguous normalized email."""

from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, email=None, **kwargs):
        identifier = email if email is not None else username
        if not identifier or password is None:
            return None

        user_model = get_user_model()
        try:
            user = user_model._default_manager.get(login_email=identifier.strip().lower())
        except user_model.DoesNotExist:
            user_model().set_password(password)
            return None
        except user_model.MultipleObjectsReturned:
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
