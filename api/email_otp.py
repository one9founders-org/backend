"""Email one-time codes for tool submission, then open a One9 account."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email, validate_ipv46_address
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.html import escape

from .models import EmailVerificationCode

logger = logging.getLogger(__name__)

User = get_user_model()
PURPOSE_TOOL_SUBMIT = EmailVerificationCode.PURPOSE_TOOL_SUBMIT


class EmailCodeError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    try:
        validate_email(email)
    except ValidationError as exc:
        raise EmailCodeError("Enter a valid email address.") from exc
    return email


def _ttl_seconds() -> int:
    return int(getattr(settings, "EMAIL_OTP_TTL_SECONDS", 600))


def _max_attempts() -> int:
    return int(getattr(settings, "EMAIL_OTP_MAX_ATTEMPTS", 5))


def _resend_seconds() -> int:
    return int(getattr(settings, "EMAIL_OTP_RESEND_SECONDS", 60))


def _max_per_hour() -> int:
    return int(getattr(settings, "EMAIL_OTP_MAX_PER_HOUR", 5))


def _max_per_ip_per_hour() -> int:
    return int(getattr(settings, "EMAIL_OTP_MAX_PER_IP_PER_HOUR", 20))


def _code_hash(email: str, code: str) -> str:
    digest = hmac.new(
        settings.SECRET_KEY.encode(),
        f"{email}:{code}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return digest


def _split_name(name: str) -> tuple[str, str]:
    parts = (name or "").strip().split(None, 1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return first_name, last_name


def _username_for_email(email: str) -> str:
    if len(email) <= 150:
        return email
    suffix = hashlib.sha256(email.encode()).hexdigest()[:12]
    return f"{email[:137]}-{suffix}"


def _active_codes(email: str):
    return EmailVerificationCode.objects.filter(
        email=email,
        purpose=PURPOSE_TOOL_SUBMIT,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
    )


def _clean_ip(ip_address: str) -> str | None:
    candidate = (ip_address or "").strip()
    if not candidate:
        return None
    try:
        validate_ipv46_address(candidate)
    except ValidationError:
        return None
    return candidate


def issue_tool_submit_code(email: str, *, ip_address: str = "") -> int:
    """Store a fresh code and email it. Returns seconds until it expires."""
    email = normalize_email(email)
    ip_address = _clean_ip(ip_address) or ""
    now = timezone.now()
    hour_ago = now - timedelta(hours=1)

    sent_recently = EmailVerificationCode.objects.filter(
        email=email,
        purpose=PURPOSE_TOOL_SUBMIT,
        created_at__gte=hour_ago,
    ).count()
    if sent_recently >= _max_per_hour():
        raise EmailCodeError(
            "Too many codes sent to that address. Try again in an hour.",
            status_code=429,
        )

    if ip_address:
        from_ip = EmailVerificationCode.objects.filter(
            ip_address=ip_address,
            purpose=PURPOSE_TOOL_SUBMIT,
            created_at__gte=hour_ago,
        ).count()
        if from_ip >= _max_per_ip_per_hour():
            raise EmailCodeError(
                "Too many verification emails from this network. Try again later.",
                status_code=429,
            )

    latest = (
        EmailVerificationCode.objects.filter(email=email, purpose=PURPOSE_TOOL_SUBMIT)
        .order_by("-created_at")
        .first()
    )
    if latest is not None:
        elapsed = (now - latest.created_at).total_seconds()
        if elapsed < _resend_seconds():
            raise EmailCodeError(
                "Wait a minute before requesting another code.",
                status_code=429,
            )

    raw_code = f"{secrets.randbelow(1_000_000):06d}"
    expires_in = _ttl_seconds()
    _active_codes(email).update(consumed_at=now)
    row = EmailVerificationCode.objects.create(
        email=email,
        purpose=PURPOSE_TOOL_SUBMIT,
        code_hash=_code_hash(email, raw_code),
        expires_at=now + timedelta(seconds=expires_in),
        ip_address=ip_address or None,
    )
    try:
        _send_code_email(email, raw_code, expires_in // 60)
    except Exception:
        row.delete()
        logger.exception("Failed to send tool-submit verification code to %s", email)
        raise EmailCodeError(
            "We could not send the verification email. Try again.",
            status_code=503,
        ) from None
    logger.info("Sent tool-submit verification code to %s", email)
    return expires_in


def match_tool_submit_code(email: str, raw_code: str) -> EmailVerificationCode:
    """Confirm the code without consuming it. Wrong guesses burn an attempt."""
    email = normalize_email(email)
    code = (raw_code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        raise EmailCodeError("Enter the 6-digit code from your email.")

    row = _active_codes(email).order_by("-created_at").first()
    if row is None:
        raise EmailCodeError("That code is invalid or expired. Request a new one.")
    if row.attempts >= _max_attempts():
        raise EmailCodeError("Too many attempts. Request a new code.")
    if not hmac.compare_digest(row.code_hash, _code_hash(email, code)):
        EmailVerificationCode.objects.filter(pk=row.pk).update(
            attempts=F("attempts") + 1
        )
        raise EmailCodeError("That code is incorrect.")
    return row


def consume_tool_submit_code(code_id: int) -> None:
    with transaction.atomic():
        row = EmailVerificationCode.objects.select_for_update().get(pk=code_id)
        now = timezone.now()
        if (
            row.consumed_at is not None
            or row.expires_at <= now
            or row.purpose != PURPOSE_TOOL_SUBMIT
        ):
            raise EmailCodeError("That code is invalid or expired. Request a new one.")
        row.consumed_at = now
        row.save(update_fields=["consumed_at"])


def ensure_verified_submitter_account(email: str, name: str):
    """Open a One9 account for a mailbox that just proved it can read mail.

    Returns (user, created). Existing accounts keep their password.
    """
    email = normalize_email(email)
    now = timezone.now()
    first_name, last_name = _split_name(name)
    existing = User.objects.filter(email__iexact=email).first()
    if existing is not None:
        updates = []
        existing.email_verified_at = now
        updates.append("email_verified_at")
        if not existing.first_name and first_name:
            existing.first_name = first_name
            updates.append("first_name")
        if not existing.last_name and last_name:
            existing.last_name = last_name
            updates.append("last_name")
        existing.save(update_fields=updates)
        return existing, False

    username = _username_for_email(email)
    if User.objects.filter(username=username).exists():
        suffix = secrets.token_hex(4)
        username = f"{username[:141]}-{suffix}"[:150]
    user = User(
        email=email,
        username=username,
        first_name=first_name,
        last_name=last_name,
        is_active=True,
        email_verified_at=now,
        profile_completed=False,
    )
    user.set_unusable_password()
    try:
        user.save()
    except IntegrityError:
        existing = User.objects.filter(email__iexact=email).first()
        if existing is None:
            raise
        existing.email_verified_at = now
        existing.save(update_fields=["email_verified_at"])
        return existing, False
    return user, True


def _send_code_email(email: str, raw_code: str, expires_minutes: int) -> None:
    subject = "Your One9Founders verification code"
    text = (
        f"Your One9Founders verification code is {raw_code}.\n\n"
        f"It expires in {expires_minutes} minutes. Enter it on the tool "
        "submission form to confirm this email. Submitting the tool also "
        "creates your One9Founders account, so we only keep real addresses.\n\n"
        "If you did not ask for this code, you can ignore this email.\n"
    )
    html = (
        "<p>Your One9Founders verification code is:</p>"
        f'<p style="font-size:28px;letter-spacing:6px;font-weight:700;">'
        f"{escape(raw_code)}</p>"
        f"<p>It expires in {expires_minutes} minutes. Enter it on the tool "
        "submission form to confirm this email. Submitting the tool also "
        "creates your One9Founders account, so we only keep real addresses.</p>"
        "<p>If you did not ask for this code, you can ignore this email.</p>"
    )
    message = EmailMultiAlternatives(
        subject=subject,
        body=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=False)
