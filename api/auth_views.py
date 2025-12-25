import os

import requests as http_requests
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from google.auth.transport import requests
from google.oauth2 import id_token
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

User = get_user_model()


def verify_turnstile(token):
    """Verify Cloudflare Turnstile token"""
    secret = os.getenv("CLOUDFLARE_TURNSTILE_SECRET")
    if not secret:
        return True  # Skip validation if not configured

    response = http_requests.post(
        "https://challenges.cloudflare.com/turnstile/v0/siteverify",
        data={"secret": secret, "response": token},
        timeout=5,
    )
    result = response.json()
    return result.get("success", False)


@api_view(["POST"])
@permission_classes([AllowAny])
def register_user(request):
    email = request.data.get("email")
    password = request.data.get("password")
    name = request.data.get("name", "")
    turnstile_token = request.data.get("turnstile_token")

    if not verify_turnstile(turnstile_token):
        return Response(
            {"error": "Verification failed"}, status=status.HTTP_400_BAD_REQUEST
        )

    if not email or not password:
        return Response(
            {"error": "Email and password required"}, status=status.HTTP_400_BAD_REQUEST
        )

    if User.objects.filter(email=email).exists():
        return Response(
            {"error": "User already exists"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        # Split full name into first and last name
        name_parts = name.strip().split(None, 1) if name else []
        first_name = name_parts[0] if len(name_parts) > 0 else ""
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        user = User.objects.create(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
            password=make_password(password),
        )

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.get_full_name() or user.first_name,
                },
            },
            status=status.HTTP_201_CREATED,
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["POST"])
@permission_classes([AllowAny])
def login_user(request):
    email = request.data.get("email")
    password = request.data.get("password")
    turnstile_token = request.data.get("turnstile_token")

    if not verify_turnstile(turnstile_token):
        return Response(
            {"error": "Verification failed"}, status=status.HTTP_400_BAD_REQUEST
        )

    if not email or not password:
        return Response(
            {"error": "Email and password required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        user = User.objects.get(email=email)
        if user.check_password(password):
            refresh = RefreshToken.for_user(user)
            return Response(
                {
                    "access": str(refresh.access_token),
                    "refresh": str(refresh),
                    "user": {
                        "id": user.id,
                        "email": user.email,
                        "name": user.get_full_name() or user.first_name,
                    },
                }
            )
        else:
            return Response(
                {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
            )
    except User.DoesNotExist:
        return Response(
            {"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED
        )


@api_view(["POST"])
@permission_classes([AllowAny])
def google_auth(request):
    credential = request.data.get("credential")
    turnstile_token = request.data.get("turnstile_token")

    if not verify_turnstile(turnstile_token):
        return Response(
            {"error": "Verification failed"}, status=status.HTTP_400_BAD_REQUEST
        )

    if not credential:
        return Response(
            {"error": "Credential required"}, status=status.HTTP_400_BAD_REQUEST
        )

    try:
        idinfo = id_token.verify_oauth2_token(
            credential, requests.Request(), os.getenv("GOOGLE_CLIENT_ID")
        )

        email = idinfo.get("email")
        name = idinfo.get("name", "")
        given_name = idinfo.get("given_name", "")
        family_name = idinfo.get("family_name", "")

        if not email:
            return Response(
                {"error": "Email not found in token"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Use given_name and family_name from Google, fallback to splitting name
        if not given_name and name:
            name_parts = name.strip().split(None, 1)
            given_name = name_parts[0] if len(name_parts) > 0 else ""
            family_name = name_parts[1] if len(name_parts) > 1 else ""

        user, created = User.objects.get_or_create(
            email=email,
            defaults={
                "username": email,
                "first_name": given_name,
                "last_name": family_name,
                "is_active": True,
            },
        )

        if not created:
            user.first_name = given_name
            user.last_name = family_name
            user.save()

        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.get_full_name() or user.first_name,
                },
            }
        )
    except Exception as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def get_current_user(request):
    user = request.user
    return Response(
        {
            "id": user.id,
            "email": user.email,
            "name": user.get_full_name() or user.first_name,
        }
    )
