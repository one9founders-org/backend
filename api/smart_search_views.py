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

logger = logging.getLogger(__name__)


class SmartSearchAnonThrottle(AnonRateThrottle):
    rate = "30/hour"
    scope = "smart_search_anon"


class SmartSearchUserThrottle(UserRateThrottle):
    rate = "200/hour"
    scope = "smart_search_user"


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def smart_search_tools(request):
    throttles = [SmartSearchAnonThrottle(), SmartSearchUserThrottle()]
    for throttle in throttles:
        if not throttle.allow_request(request, None):
            return Response(
                {"error": "Too many search requests. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    query = (request.data.get("query") or "").strip()
    if not query:
        return Response([], status=status.HTTP_200_OK)
    if len(query) > 500:
        return Response(
            {"error": "Query too long. Maximum 500 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from .smart_search import smart_search

        results = smart_search(query, top_k=20)
        logger.info("Smart search '%s' -> %d results", query, len(results))
        return Response(results)
    except Exception as e:
        logger.error("Smart search error: %s", e, exc_info=True)
        return Response([], status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([AllowAny])
@authentication_classes([JWTAuthentication])
def decompose_task_search(request):
    throttles = [SmartSearchAnonThrottle(), SmartSearchUserThrottle()]
    for throttle in throttles:
        if not throttle.allow_request(request, None):
            return Response(
                {"error": "Too many requests. Please slow down."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

    query = (request.data.get("query") or "").strip()
    if not query:
        return Response([], status=status.HTTP_200_OK)
    if len(query) > 1000:
        return Response(
            {"error": "Query too long. Maximum 1000 characters."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from .smart_search import decompose_task

        results = decompose_task(query)
        return Response(results)
    except Exception as e:
        logger.error("Decompose search error: %s", e, exc_info=True)
        return Response([], status=status.HTTP_200_OK)
