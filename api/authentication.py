from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken


class OptionalJWTAuthentication(JWTAuthentication):
    """Treat missing or invalid JWTs as anonymous instead of returning 401.

    Admin-only write endpoints then deny with 404 via IsStaffOrNotFound, so
    unauthenticated scanners cannot confirm that a protected route exists.
    """

    def authenticate(self, request):
        try:
            return super().authenticate(request)
        except (InvalidToken, AuthenticationFailed):
            return None
