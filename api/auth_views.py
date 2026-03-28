import json
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
FOUNDER_ROLES = {"founder", "cofounder"}


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


def _parse_json_field(value, default=None):
    if default is None:
        default = []
    if not value:
        return default
    if isinstance(value, list):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


@api_view(["POST"])
@permission_classes([AllowAny])
def register_user(request):
    data = request.data
    email = data.get("email", "").strip()
    password = data.get("password", "")
    name = data.get("name", "").strip()
    turnstile_token = data.get("turnstile_token", "")
    user_role = data.get("user_role", "other").strip().lower()

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

    is_founder = user_role in FOUNDER_ROLES
    is_startup = is_founder

    name_parts = name.split(None, 1) if name else []
    first_name = name_parts[0] if name_parts else ""
    last_name = name_parts[1] if len(name_parts) > 1 else ""

    founder_kwargs = {}
    if is_founder:
        founder_kwargs = {
            "startup_name": data.get("startup_name", "").strip(),
            "startup_website": data.get("website", "").strip() or None,
            "startup_stage": data.get("startup_stage", "").strip(),
            "team_size": data.get("team_size", "").strip(),
            "industry": _parse_json_field(data.get("industry")),
            "challenges": _parse_json_field(data.get("challenges")),
            "ai_tasks": _parse_json_field(data.get("ai_tasks")),
            "time_lost_per_week": data.get("time_lost_per_week", "").strip(),
            "ai_comfort_level": data.get("ai_comfort_level", "").strip(),
        }

    try:
        user = User.objects.create(
            email=email,
            username=email,
            first_name=first_name,
            last_name=last_name,
            password=make_password(password),
            is_startup=is_startup,
            user_role=user_role,
            referral_source=data.get("referral_source", "").strip(),
            profile_completed=True,
            **founder_kwargs,
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
                    "is_startup": user.is_startup,
                    "user_role": user.user_role,
                    "profile_completed": user.profile_completed,
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
                        "user_role": user.user_role,
                        "profile_completed": user.profile_completed,
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
                    "user_role": getattr(user, "user_role", ""),
                    "profile_completed": getattr(user, "profile_completed", False),
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
            "is_startup": user.is_startup,
            "user_role": getattr(user, "user_role", ""),
            "profile_completed": getattr(user, "profile_completed", False),
        }
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def complete_profile(request):
    user = request.user
    data = request.data
    user_role = (data.get("user_role") or "").strip().lower()
    is_founder = user_role in FOUNDER_ROLES

    user.user_role = user_role
    user.referral_source = (data.get("referral_source") or "").strip()
    user.profile_completed = True
    user.is_startup = is_founder

    if is_founder:
        user.startup_name = (data.get("startup_name") or "").strip()
        user.startup_website = (data.get("website") or "").strip() or None
        user.startup_stage = (data.get("startup_stage") or "").strip()
        user.team_size = (data.get("team_size") or "").strip()
        user.industry = _parse_json_field(data.get("industry"))
        user.challenges = _parse_json_field(data.get("challenges"))
        user.ai_tasks = _parse_json_field(data.get("ai_tasks"))
        user.time_lost_per_week = (data.get("time_lost_per_week") or "").strip()
        user.ai_comfort_level = (data.get("ai_comfort_level") or "").strip()

    user.save()
    return Response({"success": True, "user_role": user.user_role})
