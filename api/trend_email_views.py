"""Internal endpoint: email trend-blog draft digests for human approval."""

from __future__ import annotations

import logging
from html import escape

from django.conf import settings
from django.core.mail import send_mail
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from .permissions import IsStaffOrPipelineKey

logger = logging.getLogger(__name__)


def _approval_recipients(override: str | None = None) -> list[str]:
    raw = (override or getattr(settings, "TREND_APPROVAL_EMAIL", "") or "").strip()
    if not raw:
        raw = "hello@one9founders.com"
    return [part.strip() for part in raw.split(",") if part.strip()]


def _render_bodies(drafts: list[dict], note: str) -> tuple[str, str]:
    lines_txt = [
        "One9Founders — trend blog drafts ready for your approval",
        "",
        "These are DRAFTS only. Nothing is live until you promote a post into the blog.",
        "",
    ]
    if note:
        lines_txt.extend([f"Note: {note}", ""])

    lines_html = [
        "<h2>Trend blog drafts ready for approval</h2>",
        "<p>These are <strong>drafts only</strong>. Nothing is live until you promote a post into "
        "<code>src/lib/blog.ts</code> (or the content sheet).</p>",
    ]
    if note:
        lines_html.append(f"<p><em>{escape(note)}</em></p>")
    lines_html.append("<ol>")

    for i, draft in enumerate(drafts, start=1):
        title = str(draft.get("title") or "Untitled").strip()
        filename = str(draft.get("filename") or "").strip()
        geo = str(draft.get("geo") or "").strip()
        traffic = str(draft.get("approxTraffic") or draft.get("traffic") or "").strip()
        topic = str(draft.get("topic") or "").strip()
        summary = str(draft.get("summary") or "").strip()
        source = str(draft.get("source") or draft.get("link") or "").strip()

        meta_bits = [b for b in [geo and f"geo={geo}", traffic and f"~{traffic} searches"] if b]
        meta = f" ({', '.join(meta_bits)})" if meta_bits else ""

        lines_txt.append(f"{i}. {title}{meta}")
        if topic:
            lines_txt.append(f"   Topic: {topic}")
        if filename:
            lines_txt.append(f"   File: content/blog/drafts/{filename}")
        if summary:
            lines_txt.append(f"   {summary}")
        if source:
            lines_txt.append(f"   Source: {source}")
        lines_txt.append("")

        lines_html.append("<li>")
        lines_html.append(f"<p><strong>{escape(title)}</strong>{escape(meta)}</p>")
        if topic:
            lines_html.append(f"<p>Topic: {escape(topic)}</p>")
        if filename:
            lines_html.append(
                f"<p>File: <code>content/blog/drafts/{escape(filename)}</code></p>"
            )
        if summary:
            lines_html.append(f"<p>{escape(summary)}</p>")
        if source:
            lines_html.append(
                f'<p><a href="{escape(source, quote=True)}">Trend source</a></p>'
            )
        lines_html.append("</li>")

    lines_html.append("</ol>")
    lines_html.append(
        "<p><strong>How to approve:</strong> edit the draft, then promote it into the live blog "
        "and delete/archive the draft file. Reply to this email if you want changes to the "
        "automation.</p>"
    )
    lines_txt.extend(
        [
            "How to approve:",
            "1. Open content/blog/drafts/<filename>",
            "2. Rewrite the checklist into real analysis + deep links",
            "3. Promote into src/lib/blog.ts (or content sheet → npm run content:generate)",
            "4. Delete the draft file after publish",
            "",
            "— One9Founders content:trends",
        ]
    )
    return "\n".join(lines_txt), "\n".join(lines_html)


@extend_schema(exclude=True)
@api_view(["POST"])
@permission_classes([IsStaffOrPipelineKey])
def send_trend_approval_email(request):
    """
    Pipeline hook: email a human digest of trend→blog drafts.

    Auth: staff JWT/session OR header X-Pipeline-Key matching PIPELINE_API_KEY.
    Body JSON:
      {
        "drafts": [{ "title", "filename", "geo", "approxTraffic", "topic", "summary", "source" }],
        "to": "optional@override.com",   # optional; else TREND_APPROVAL_EMAIL
        "note": "optional context"
      }
    """
    drafts = request.data.get("drafts")
    if not isinstance(drafts, list) or not drafts:
        return Response(
            {"detail": "drafts must be a non-empty list"},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if len(drafts) > 30:
        return Response(
            {"detail": "drafts capped at 30 per email"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    recipients = _approval_recipients(
        request.data.get("to") if isinstance(request.data.get("to"), str) else None
    )
    note = request.data.get("note") if isinstance(request.data.get("note"), str) else ""
    text_body, html_body = _render_bodies(drafts, note)
    subject = f"[One9Founders] {len(drafts)} trend blog draft(s) need approval"

    try:
        sent = send_mail(
            subject=subject,
            message=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            html_message=html_body,
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send trend approval email to %s", recipients)
        return Response(
            {"detail": "email send failed"},
            status=status.HTTP_502_BAD_GATEWAY,
        )

    return Response(
        {
            "status": "ok",
            "sent": sent,
            "recipients": recipients,
            "draft_count": len(drafts),
        }
    )
