import logging

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.authentication import JWTAuthentication

from api.models import JobStack
from api.stack_assemble import assemble_and_save, save_person_stack

logger = logging.getLogger(__name__)


class StackAnonThrottle(AnonRateThrottle):
    rate = "20/hour"
    scope = "stack_assemble_anon"


class StackUserThrottle(UserRateThrottle):
    rate = "100/hour"
    scope = "stack_assemble_user"


def _throttle_or_429(request):
    for throttle in (StackAnonThrottle(), StackUserThrottle()):
        if not throttle.allow_request(request, None):
            return Response(
                {"error": "Too many stack requests. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
    return None


def _stack_payload(stack: JobStack) -> dict:
    return {
        "public_id": stack.public_id,
        "query": stack.query,
        "title": stack.title,
        "blurb": stack.blurb,
        "cash_out": stack.cash_out,
        "source": stack.source,
        "lanes": stack.lanes,
        "created_at": stack.created_at.isoformat() if stack.created_at else None,
        "url_path": f"/stack/{stack.public_id}",
    }


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def assemble_stack(request):
    blocked = _throttle_or_429(request)
    if blocked:
        return blocked

    query = (request.data.get("query") or "").strip()
    if not query:
        return Response(
            {"error": "Tell us the job to assemble a stack."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(query) > 500:
        return Response(
            {"error": "Query too long. Maximum 500 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    source = (request.data.get("source") or "agent").strip().lower()
    if source not in ("agent", "person"):
        source = "agent"

    try:
        stack = assemble_and_save(
            query,
            source=source,
            created_by=request.user,
        )
        return Response(_stack_payload(stack), status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error("Assemble stack failed: %s", e, exc_info=True)
        return Response(
            {"error": "Could not assemble a stack right now."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def save_stack(request):
    blocked = _throttle_or_429(request)
    if blocked:
        return blocked

    query = (request.data.get("query") or "").strip()
    if not query:
        return Response(
            {"error": "A job query is required."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(query) > 500:
        return Response(
            {"error": "Query too long. Maximum 500 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    lanes = request.data.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        return Response(
            {"error": "lanes must be a non-empty list."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        stack = save_person_stack(
            query=query,
            title=(request.data.get("title") or "")[:200],
            blurb=(request.data.get("blurb") or "")[:400],
            cash_out=(request.data.get("cash_out") or "")[:400],
            lanes=lanes,
            created_by=request.user,
        )
        return Response(_stack_payload(stack), status=status.HTTP_201_CREATED)
    except Exception as e:
        logger.error("Save stack failed: %s", e, exc_info=True)
        return Response(
            {"error": "Could not save this stack."},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
@permission_classes([AllowAny])
def get_stack(request, public_id: str):
    public_id = (public_id or "").strip().lower()
    stack = JobStack.objects.filter(public_id=public_id).first()
    if not stack:
        return Response({"error": "Stack not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(_stack_payload(stack))
