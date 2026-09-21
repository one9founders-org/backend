"""Email approved tool submitters that their listing is live.

Skips anyone with listed_email_sent_at set (including the earlier manual
campaign once those rows are marked). Default is dry-run.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from api.models import ToolSubmission
from api.submission_mail import (
    EXTENSION_SUBMITTER,
    community_submission_queryset,
    pending_listed_email_queryset,
    render_listed_email,
    send_listed_email,
)


class Command(BaseCommand):
    help = (
        "Notify approved submitters that their tool is listed. "
        "Dry-run by default; pass --send to deliver via SES."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--send",
            action="store_true",
            help="Actually send emails (default is dry-run).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Max emails to send this run (0 = no limit).",
        )
        parser.add_argument(
            "--include-sent",
            action="store_true",
            help="Include rows that already have listed_email_sent_at (resend).",
        )
        parser.add_argument(
            "--email",
            action="append",
            default=[],
            help="Only this submitter email (repeatable).",
        )
        parser.add_argument(
            "--mark-sent-file",
            type=str,
            default="",
            help=(
                "Path to a file of emails (one per line) already mailed offline. "
                "Marks matching approved submissions without sending."
            ),
        )
        parser.add_argument(
            "--approved-after",
            type=str,
            default="",
            help="Only submissions updated/approved after this ISO datetime.",
        )

    def handle(self, *args, **options):
        mark_path = (options.get("mark_sent_file") or "").strip()
        if mark_path:
            self._mark_already_sent(mark_path)
            return

        qs = (
            community_submission_queryset()
            if options["include_sent"]
            else pending_listed_email_queryset()
        )
        emails = [e.strip().lower() for e in options["email"] if e and e.strip()]
        if emails:
            qs = qs.filter(submitter_email__in=emails)

        after = (options.get("approved_after") or "").strip()
        if after:
            parsed = parse_datetime(after)
            if not parsed:
                self.stderr.write(f"Invalid --approved-after: {after}")
                return
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
            qs = qs.filter(updated_at__gte=parsed)

        limit = options["limit"]
        rows = list(qs[:limit] if limit and limit > 0 else qs)
        self.stdout.write(f"Candidates: {len(rows)} (dry_run={not options['send']})")

        sent = skipped = errors = 0
        for submission in rows:
            subject, text, _html = render_listed_email(submission)
            tool = submission.approved_tool
            preview = (
                f"{submission.submitter_email} | {submission.name} | "
                f"tool={tool.slug if tool else '-'} | {subject}"
            )
            if not options["send"]:
                self.stdout.write(f"[dry-run] {preview}")
                self.stdout.write(text.splitlines()[0][:120])
                skipped += 1
                continue
            try:
                ok = send_listed_email(submission)
                if ok:
                    sent += 1
                    self.stdout.write(self.style.SUCCESS(f"sent {preview}"))
                else:
                    errors += 1
                    self.stderr.write(f"failed {preview}")
            except Exception as exc:
                errors += 1
                self.stderr.write(f"error {preview}: {exc}")

        self.stdout.write(
            f"Done. sent={sent} dry_run_or_skipped={skipped} errors={errors}"
        )

    def _mark_already_sent(self, path: str) -> None:
        emails = []
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            emails.append(line.lower())
        if not emails:
            self.stderr.write("No emails in mark-sent file.")
            return
        now = timezone.now()
        updated = (
            ToolSubmission.objects.filter(
                status="approved",
                listed_email_sent_at__isnull=True,
                submitter_email__in=emails,
            )
            .exclude(submitter_email__iexact=EXTENSION_SUBMITTER)
            .update(listed_email_sent_at=now)
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Marked listed_email_sent_at on {updated} submission(s) "
                f"from {len(emails)} email(s) in {path}."
            )
        )
