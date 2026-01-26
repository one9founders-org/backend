import requests
from django.conf import settings
from rest_framework import status
from rest_framework.response import Response


def verify_recaptcha(token: str, action: str = None) -> dict:
    """
    Verify a reCAPTCHA v3 token with Google's API.

    Args:
        token: The reCAPTCHA token from the frontend
        action: Optional action name to verify (e.g., 'submit_tool', 'write_review')

    Returns:
        dict with keys:
            - success: bool indicating if verification passed
            - score: float score from 0.0 to 1.0 (1.0 is very likely human)
            - action: the action name if provided
            - error: error message if verification failed
    """
    if not settings.RECAPTCHA_SECRET_KEY:
        return {"success": True, "score": 1.0, "error": None}

    if not token:
        return {"success": False, "score": 0.0, "error": "No reCAPTCHA token provided"}

    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": settings.RECAPTCHA_SECRET_KEY,
                "response": token,
            },
            timeout=5,
        )
        result = response.json()

        if not result.get("success"):
            error_codes = result.get("error-codes", [])
            return {
                "success": False,
                "score": 0.0,
                "error": f"reCAPTCHA verification failed: {error_codes}",
            }

        score = result.get("score", 0.0)
        result_action = result.get("action", "")

        if action and result_action != action:
            return {
                "success": False,
                "score": score,
                "error": f"Action mismatch: expected {action}, got {result_action}",
            }

        if score < settings.RECAPTCHA_SCORE_THRESHOLD:
            threshold = settings.RECAPTCHA_SCORE_THRESHOLD
            return {
                "success": False,
                "score": score,
                "error": f"Score too low: {score} < {threshold}",
            }

        return {"success": True, "score": score, "action": result_action, "error": None}

    except requests.RequestException as e:
        return {"success": False, "score": 0.0, "error": f"Request failed: {str(e)}"}


def recaptcha_required(action: str = None):
    """
    Decorator for views that require reCAPTCHA verification.

    Usage:
        @api_view(['POST'])
        @recaptcha_required(action='submit_tool')
        def submit_tool(request):
            ...
    """

    def decorator(view_func):
        def wrapper(request, *args, **kwargs):
            token = request.data.get("recaptcha_token") or request.headers.get(
                "X-Recaptcha-Token"
            )

            result = verify_recaptcha(token, action)

            if not result["success"]:
                return Response(
                    {"error": result["error"], "recaptcha_failed": True},
                    status=status.HTTP_403_FORBIDDEN,
                )

            request.recaptcha_score = result.get("score", 0.0)
            return view_func(request, *args, **kwargs)

        wrapper.__name__ = view_func.__name__
        wrapper.__doc__ = view_func.__doc__
        return wrapper

    return decorator
