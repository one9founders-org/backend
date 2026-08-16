from unittest.mock import patch

import pytest

from api.hygiene.assess import empty_usage, token_cost_usd
from api.hygiene.assess_run import SpendGuard, clamp_budget, run
from tests.factories import ToolFactory


class TestSpendGuard:
    def test_clamp_caps_at_fifty(self):
        assert clamp_budget(80) == 50.0
        assert clamp_budget(40) == 40.0

    def test_clamp_rejects_zero(self):
        with pytest.raises(ValueError):
            clamp_budget(0)

    def test_exceeded_after_running_total_crosses_budget(self):
        guard = SpendGuard(budget_usd=0.001, model="gpt-4o-mini")
        assert guard.exceeded() is False
        # ~6667 prompt tokens at $0.15/1M is $0.001
        guard.add(7000, 0)
        assert guard.usd == pytest.approx(token_cost_usd(7000, 0, "gpt-4o-mini"))
        assert guard.exceeded() is True


@pytest.mark.django_db
class TestAssessRunBudget:
    def test_run_aborts_when_budget_is_exhausted(self, tmp_path, settings):
        settings.ENRICHMENT_LOG_DIR = tmp_path
        ToolFactory.create_batch(3, website="https://example.com")

        fake_usage = {
            "prompt_tokens": 20_000,
            "completion_tokens": 0,
            "cost_usd": token_cost_usd(20_000, 0, "gpt-4o-mini"),
        }
        fake_result = {
            "scored": {},
            "unassessed": [],
            "manual_only": [],
            "criteria_completed": 0,
            "overall_score": None,
            "security_criterion_score": None,
            "usage": fake_usage,
        }

        with (
            patch(
                "api.hygiene.assess_run.collect_evidence",
                return_value={
                    "transport": {
                        "url": "https://example.com",
                        "text": "https",
                        "present": True,
                    }
                },
            ),
            patch("api.hygiene.assess_run.assess", return_value=fake_result),
        ):
            summary = run(limit=3, apply=False, budget_usd=0.002, only_unassessed=False)

        # 20k tokens * $0.15/1M = $0.003 per call; budget $0.002 aborts after 1.
        assert summary["aborted"] is True
        assert summary["processed"] == 1
        assert summary["spent_usd"] > 0

    def test_apply_does_not_call_tool_save_enrichment(self, tmp_path, settings):
        settings.ENRICHMENT_LOG_DIR = tmp_path
        tool = ToolFactory(
            name="Apply Safe",
            website="https://example.com",
            tags=["productivity"],
        )
        scored = {
            cid: {
                "score": 6,
                "evidence_url": "https://example.com/privacy",
                "reasoning": "ok",
            }
            for cid in (
                "security_privacy",
                "functionality",
                "pricing_value",
                "integrations",
                "support",
                "update_frequency",
            )
        }
        fake_result = {
            "scored": scored,
            "unassessed": [],
            "manual_only": [],
            "criteria_completed": 6,
            "overall_score": 3.0,
            "security_criterion_score": 12,
            "usage": empty_usage(),
        }

        with (
            patch("api.ai_enrichment.enrich_tool_data") as enrich,
            patch(
                "api.hygiene.assess_run.collect_evidence",
                return_value={
                    "homepage": {"url": "https://example.com", "present": True}
                },
            ),
            patch("api.hygiene.assess_run.assess", return_value=fake_result),
        ):
            summary = run(limit=1, apply=True, only_unassessed=False)

        tool.refresh_from_db()
        assert summary["updated"] == 1
        assert tool.criteria_completed == 6
        assert tool.assessment_detail["hands_on"] is False
        enrich.assert_not_called()
