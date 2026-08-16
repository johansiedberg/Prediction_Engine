from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q


class EmailAuthBackend(ModelBackend):
    """
    Authenticates against settings.AUTH_USER_MODEL by email (case-insensitive)
    or username fallback.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        UserModel = get_user_model()
        email = kwargs.get('email', username)
        if email is None or password is None:
            return None

        try:
            # Query by email (case-insensitive) or username
            user = UserModel.objects.filter(
                Q(email__iexact=email) | Q(username__iexact=email)
            ).first()
        except UserModel.DoesNotExist:
            return None

        if user and user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
