"""Save a founder submission first, then enrich it without losing the row."""

from __future__ import annotations

import logging

from django.db import transaction

logger = logging.getLogger(__name__)


def submission_requirements(submission) -> list[str]:
    missing = []
    if not (submission.website or "").strip():
        missing.append("official URL")
    if len((submission.description or "").strip()) < 40:
        missing.append("a description of what the product does")
    if submission.enrichment_status == "failed":
        missing.append("automatic draft enrichment failed; a reviewer can still continue")
    return missing


def enrich_submission(submission_id: int) -> None:
    from .ai_enrichment import enrich_tool_data
    from .models import ToolSubmission

    submission = ToolSubmission.objects.filter(pk=submission_id).first()
    if submission is None:
        return
    if submission.enrichment_status == "succeeded" and submission.enriched_data:
        return
    attempts = submission.enrichment_attempts + 1
    try:
        data = enrich_tool_data(
            submission.name, submission.description, submission.website
        )
    except Exception as exc:
        logger.warning(
            "Submission %s enrichment failed: %s", submission_id, exc
        )
        ToolSubmission.objects.filter(pk=submission_id).update(
            enrichment_status="failed",
            enrichment_error=str(exc)[:500],
            enrichment_attempts=attempts,
        )
        return
    ToolSubmission.objects.filter(pk=submission_id).update(
        enriched_data=data or {},
        enrichment_status="succeeded" if data else "failed",
        enrichment_error="" if data else "Enrichment returned no data",
        enrichment_attempts=attempts,
    )


def schedule_submission_enrichment(submission_id: int) -> None:
    """Run after the row is committed. Failures update status and keep the row."""

    def _run() -> None:
        try:
            enrich_submission(submission_id)
        except Exception:
            logger.exception("Submission enrichment crashed for %s", submission_id)

    transaction.on_commit(_run)
