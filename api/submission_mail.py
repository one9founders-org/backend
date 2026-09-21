"""Personalized “your tool is listed” emails for approved submissions."""

from __future__ import annotations

import logging
from html import escape

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import ToolSubmission

logger = logging.getLogger(__name__)

EXTENSION_SUBMITTER = "extension@one9founders.com"
PUBLIC_SITE_URL = getattr(
    settings, "PUBLIC_SITE_URL", "https://www.one9founders.com"
).rstrip("/")
AMIT_LINKEDIN = "https://www.linkedin.com/in/amitbhartiya33/"
COMPANY_LINKEDIN = "https://in.linkedin.com/company/one9founders"
COMPANY_INSTAGRAM = "https://www.instagram.com/one9founders"


def community_submission_queryset():
    """Approved human submissions linked to a live tool."""
    return (
        ToolSubmission.objects.filter(status="approved", approved_tool__isnull=False)
        .exclude(submitter_email__iexact=EXTENSION_SUBMITTER)
        .select_related("approved_tool")
        .order_by("-created_at")
    )


def pending_listed_email_queryset():
    return community_submission_queryset().filter(listed_email_sent_at__isnull=True)


def _greeting_name(submission: ToolSubmission) -> str:
    name = (submission.submitter_name or "").strip()
    if name:
        return name.split()[0]
    email = (submission.submitter_email or "").strip()
    return email.split("@")[0] if email else "there"


def _tool_urls(submission: ToolSubmission) -> tuple[str, str, str]:
    tool = submission.approved_tool
    slug = (tool.slug if tool else "") or ""
    listing = f"{PUBLIC_SITE_URL}/tool/{slug}" if slug else PUBLIC_SITE_URL
    edit = f"{listing}/edit" if slug else f"{PUBLIC_SITE_URL}/submit"
    account = f"{PUBLIC_SITE_URL}/?login=1"
    return listing, edit, account


def render_listed_email(submission: ToolSubmission) -> tuple[str, str, str]:
    """Return (subject, text_body, html_body) for one submission."""
    tool = submission.approved_tool
    tool_name = (tool.name if tool else submission.name) or submission.name
    first = _greeting_name(submission)
    listing, edit, account = _tool_urls(submission)

    subject = f"You're live on One9Founders — {tool_name}"

    text = f"""Hi {first},

Great news — {tool_name} is now listed on One9Founders.

Your public listing:
{listing}

Update your listing anytime (sign in with {submission.submitter_email}):
{edit}

Your account / owned listings:
{account}

We're featuring community submissions on the homepage so founders
browsing One9Founders can discover tools like yours. A few ways to
help traction:

1. Share your listing with your users and on LinkedIn / Instagram
2. Ask your community to open the page and upvote / engage with the listing
3. Follow us and say hello — we amplify founder-built AI & SaaS products:
   - Amit (founder): {AMIT_LINKEDIN}
   - One9Founders on LinkedIn: {COMPANY_LINKEDIN}
   - Instagram: {COMPANY_INSTAGRAM}

One9Founders is actively helping teams with AI and SaaS discovery,
listing, consulting, and implementation. If you want a deeper
partnership (featured placement, founder intros, or AI/SaaS services),
just reply to this email.

Welcome to the directory — glad to have {tool_name} with us.

— Amit & the One9Founders team
{PUBLIC_SITE_URL}
"""

    safe_name = escape(tool_name)
    safe_first = escape(first)
    safe_email = escape(submission.submitter_email)
    safe_listing = escape(listing, quote=True)
    safe_edit = escape(edit, quote=True)
    safe_account = escape(account, quote=True)

    html = f"""<!DOCTYPE html>
<html>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
 line-height: 1.5; color: #1a1a1a;">
  <p>Hi {safe_first},</p>
  <p>Great news — <strong>{safe_name}</strong> is now listed on One9Founders.</p>
  <p>
    <a href="{safe_listing}">Your public listing</a><br>
    <a href="{safe_edit}">Edit your listing</a>
    (sign in with <code>{safe_email}</code>)<br>
    <a href="{safe_account}">Your account / owned listings</a>
  </p>
  <p>
    We're featuring community submissions on the homepage so founders browsing
    One9Founders can discover tools like yours.
  </p>
  <p><strong>Help traction:</strong></p>
  <ol>
    <li>Share your listing with your users and on LinkedIn / Instagram</li>
    <li>Ask your community to open the page and upvote / engage with the listing</li>
    <li>
      Follow us and say hello — we amplify founder-built AI &amp; SaaS products:<br>
      <a href="{escape(AMIT_LINKEDIN, quote=True)}">Amit on LinkedIn</a> ·
      <a href="{escape(COMPANY_LINKEDIN, quote=True)}">One9Founders LinkedIn</a> ·
      <a href="{escape(COMPANY_INSTAGRAM, quote=True)}">Instagram</a>
    </li>
  </ol>
  <p>
    One9Founders is actively helping teams with AI and SaaS discovery, listing,
    consulting, and implementation. If you want a deeper partnership (featured
    placement, founder intros, or AI/SaaS services), just reply to this email.
  </p>
  <p>Welcome to the directory — glad to have {safe_name} with us.</p>
  <p>— Amit &amp; the One9Founders team<br>
  <a href="{escape(PUBLIC_SITE_URL, quote=True)}">{escape(PUBLIC_SITE_URL)}</a></p>
</body>
</html>
"""
    return subject, text, html


def send_listed_email(submission: ToolSubmission, *, mark_sent: bool = True) -> bool:
    """Send one listing email. Returns True if SES accepted it."""
    if not submission.submitter_email:
        return False
    subject, text, html = render_listed_email(submission)
    sent = send_mail(
        subject=subject,
        message=text,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[submission.submitter_email.strip()],
        html_message=html,
        fail_silently=False,
    )
    if sent and mark_sent:
        ToolSubmission.objects.filter(pk=submission.pk).update(
            listed_email_sent_at=timezone.now()
        )
        submission.listed_email_sent_at = timezone.now()
    return bool(sent)
