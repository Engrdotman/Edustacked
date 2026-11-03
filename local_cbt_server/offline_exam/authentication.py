import hashlib

from django.utils import timezone
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import StudentAccessToken


class LocalStudent:
    is_authenticated = True
    is_anonymous = False
    is_active = True
    is_staff = False

    def __init__(self, credential):
        self.credential = credential
        self.pk = credential.pk
        self.id = credential.pk
        self.username = credential.admission_number
        self.display_name = credential.display_name


class StudentTokenAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        return "Bearer"

    def authenticate(self, request):
        header = get_authorization_header(request).split()
        if not header:
            return None
        if len(header) != 2 or header[0].lower() != b"bearer":
            raise AuthenticationFailed("Use a valid local student bearer token.")
        raw_token = header[1].decode("utf-8")
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        record = StudentAccessToken.objects.select_related("student").filter(token_hash=token_hash).first()
        if not record or not record.is_valid:
            raise AuthenticationFailed("The local student session has expired or was revoked.")
        return LocalStudent(record.student), record
