import csv
import json
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.test.utils import override_settings

from api.tool_enrichment import batch_slug_from_csv, parse_pricing, parse_tool_id
from tests.factories import CategoryFactory, ToolFactory


class TestEnrichmentParsers:
    def test_parse_pricing_type_and_models(self):
        assert parse_pricing("Paid") == ("pricing_type", "paid")
        assert parse_pricing("Free Trial") == ("pricing_models", ["trial"])
        assert parse_pricing("free, paid") == ("pricing_models", ["free", "paid"])
        assert parse_pricing("$20/mo") is None

    def test_parse_tool_id_accepts_id_column(self):
        assert parse_tool_id({"tool_id": "42"}) == 42
        assert parse_tool_id({"id": "7"}) == 7
        assert parse_tool_id({"tool_id": "abc"}) is None

    def test_batch_slug_strips_approved_prefix(self):
        assert batch_slug_from_csv(Path("approved_batch1.csv")) == "batch1"
        assert batch_slug_from_csv(Path("/tmp/approved_batch1.csv")) == "batch1"
        assert batch_slug_from_csv(Path("tools.csv")) == "tools"


def _write_csv(path: Path, rows: list[dict], fieldnames=None):
    fieldnames = fieldnames or [
        "tool_id",
        "description",
        "pricing",
        "pros",
        "cons",
        "category",
        "approved",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


@pytest.mark.django_db
class TestImportToolEnrichment:
    def test_dry_run_default_does_not_write(self, tmp_path):
        writing = CategoryFactory(name="Writing", slug="writing")
        tool = ToolFactory(
            name="Writer",
            description="Old description",
            pricing_type="freemium",
            categories=[writing],
            criteria_completed=10,
            security_criterion_score=18,
        )
        csv_path = tmp_path / "enrichment.csv"
        _write_csv(
            csv_path,
            [
                {
                    "tool_id": tool.id,
                    "description": "New description",
                    "pricing": "Paid",
                    "pros": "Fast",
                    "cons": "Expensive",
                    "category": "Writing",
                    "approved": "yes",
                }
            ],
        )

        out = StringIO()
        err = StringIO()
        call_command(
            "import_tool_enrichment",
            f"--file={csv_path}",
            stdout=out,
            stderr=err,
        )

        tool.refresh_from_db()
        assert tool.description == "Old description"
        assert tool.pricing_type == "freemium"
        assert tool.criteria_completed == 10
        assert tool.security_criterion_score == 18
        assert "DRY RUN" in out.getvalue()
        assert "Tools updated: 1" in out.getvalue()
        assert "pros" in err.getvalue()

    def test_skips_unapproved_and_missing_tools(self, tmp_path):
        writing = CategoryFactory(name="Writing", slug="writing")
        tool = ToolFactory(
            name="Kept",
            description="Keep me",
            categories=[writing],
        )
        csv_path = tmp_path / "enrichment.csv"
        _write_csv(
            csv_path,
            [
                {
                    "tool_id": tool.id,
                    "description": "Should not apply",
                    "pricing": "",
                    "pros": "",
                    "cons": "",
                    "category": "",
                    "approved": "no",
                },
                {
                    "tool_id": 999999,
                    "description": "Missing tool",
                    "pricing": "",
                    "pros": "",
                    "cons": "",
                    "category": "",
                    "approved": "YES",
                },
            ],
        )

        out = StringIO()
        err = StringIO()
        call_command(
            "import_tool_enrichment",
            f"--file={csv_path}",
            stdout=out,
            stderr=err,
        )

        tool.refresh_from_db()
        assert tool.description == "Keep me"
        output = out.getvalue()
        assert "Skipped (not approved): 1" in output
        assert "Skipped (tool not found): 1" in output
        assert "Tools updated: 0" in output
        assert "not found" in err.getvalue()

    def test_apply_writes_log_and_updates_then_revert_restores(self, tmp_path):
        writing = CategoryFactory(name="Writing", slug="writing")
        code = CategoryFactory(name="Code", slug="code")
        tool = ToolFactory(
            name="Switchable",
            description="Before",
            pricing_type="free",
            categories=[writing],
            criteria_completed=7,
            security_criterion_score=12,
        )
        csv_path = tmp_path / "approved_batch1.csv"
        log_dir = tmp_path / "enrichment-logs"
        _write_csv(
            csv_path,
            [
                {
                    "tool_id": tool.id,
                    "description": "After",
                    "pricing": "freemium",
                    "pros": "Nice",
                    "cons": "",
                    "category": "Code",
                    "approved": "yes",
                }
            ],
        )

        out = StringIO()
        with override_settings(ENRICHMENT_LOG_DIR=log_dir):
            call_command(
                "import_tool_enrichment",
                f"--file={csv_path}",
                "--apply",
                stdout=out,
            )

        tool.refresh_from_db()
        assert tool.description == "After"
        assert tool.pricing_type == "freemium"
        assert list(tool.categories.values_list("name", flat=True)) == ["Code"]
        assert tool.criteria_completed == 7
        assert tool.security_criterion_score == 12
        assert "APPLY" in out.getvalue()

        logs = list(log_dir.glob("*-batch1.json"))
        assert len(logs) == 1
        assert logs[0].name.endswith("-batch1.json")
        payload = json.loads(logs[0].read_text())
        assert payload["tools"][0]["tool_id"] == tool.id
        fields = {change["field"] for change in payload["tools"][0]["changes"]}
        assert fields == {"description", "pricing_type", "categories"}

        revert_out = StringIO()
        call_command(
            "revert_tool_enrichment",
            f"--file={logs[0]}",
            stdout=revert_out,
        )
        tool.refresh_from_db()
        assert tool.description == "Before"
        assert tool.pricing_type == "free"
        assert list(tool.categories.values_list("name", flat=True)) == ["Writing"]
        assert tool.criteria_completed == 7
        assert "Tools reverted: 1" in revert_out.getvalue()
        assert code.slug == "code"

    def test_apply_flag_ignored_when_dry_run_also_passed(self, tmp_path):
        writing = CategoryFactory(name="Writing", slug="writing")
        tool = ToolFactory(
            name="Safe",
            description="Original",
            categories=[writing],
        )
        csv_path = tmp_path / "enrichment.csv"
        _write_csv(
            csv_path,
            [
                {
                    "tool_id": tool.id,
                    "description": "Changed",
                    "pricing": "",
                    "pros": "",
                    "cons": "",
                    "category": "",
                    "approved": "yes",
                }
            ],
        )

        out = StringIO()
        call_command(
            "import_tool_enrichment",
            f"--file={csv_path}",
            "--apply",
            "--dry-run",
            stdout=out,
        )
        tool.refresh_from_db()
        assert tool.description == "Original"
        assert "DRY RUN" in out.getvalue()
