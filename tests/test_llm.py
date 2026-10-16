import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api.hygiene.assess import assess
from api.hygiene.assess_run import SpendGuard
from api.hygiene.enrich import accepts_write, enrich
from api.llm import (
    ClaudeCallError,
    SpendCapExceeded,
    SpendMeter,
    complete_json,
    spend_cap,
    submit_json_batch,
    token_cost_usd,
)
from api.verified_listings import protected_from_ai


def test_opus_55_rates_match_the_price_card():
    assert token_cost_usd(input_tokens=1_000_000) == pytest.approx(4.0)
    assert token_cost_usd(output_tokens=1_000_000) == pytest.approx(20.0)
    assert token_cost_usd(cache_creation_input_tokens=1_000_000) == pytest.approx(5.0)
    assert token_cost_usd(cache_read_input_tokens=1_000_000) == pytest.approx(0.20)
    assert token_cost_usd(web_search_requests=1) == pytest.approx(0.01)
    assert token_cost_usd(input_tokens=1_000_000, batch=True) == pytest.approx(2.0)
    assert token_cost_usd(output_tokens=1_000_000, batch=True) == pytest.approx(10.0)


def test_reported_cost_overrides_token_reprice():
    guard = SpendGuard(budget_usd=1, model="gpt-4o-mini")
    guard.add(1_000_000, 0, cost_usd=4.0)
    assert guard.usd == pytest.approx(4.0)
    assert guard.exceeded() is True


def test_protected_listings_are_not_for_the_model():
    assert protected_from_ai(SimpleNamespace(verified=True, slug="acme")) is True
    assert protected_from_ai(SimpleNamespace(verified=False, slug="claude")) is True
    assert protected_from_ai(SimpleNamespace(verified=False, slug="acme")) is False


class _Usage:
    input_tokens = 100
    output_tokens = 50
    cache_creation_input_tokens = 0
    cache_read_input_tokens = 0
    server_tool_use = None


class _Messages:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


class _Client:
    def __init__(self, response):
        self.messages = _Messages(response)

    @property
    def batches(self):
        return self.messages


def _response(text, stop="end_turn", output_tokens=50):
    usage = _Usage()
    usage.output_tokens = output_tokens
    return SimpleNamespace(
        stop_reason=stop,
        content=[SimpleNamespace(type="text", text=text)],
        usage=usage,
    )


SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["ok"],
    "properties": {"ok": {"type": "boolean"}},
}


def test_complete_json_caches_a_long_system_prompt(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    settings.HYGIENE_CLAUDE_EFFORT = "medium"
    client = _Client(_response('{"ok": true}'))
    with patch("api.llm._client", return_value=client):
        data, usage = complete_json(
            system="x" * 2000,
            user="Set ok true.",
            schema=SCHEMA,
            max_tokens=1000,
        )
    assert data == {"ok": True}
    assert usage.cost_usd > 0
    system = client.messages.calls[0]["system"]
    assert system[0]["cache_control"] == {"type": "ephemeral"}
    assert client.messages.calls[0]["output_config"]["effort"] == "medium"
    assert client.messages.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_refusal_and_truncation_are_errors(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    with patch(
        "api.llm._client", return_value=_Client(_response("{}", stop="refusal"))
    ):
        with pytest.raises(ClaudeCallError, match="refused"):
            complete_json(system="s", user="u", schema=SCHEMA)
    with patch(
        "api.llm._client",
        return_value=_Client(_response('{"ok": true}', stop="max_tokens")),
    ):
        with pytest.raises(ClaudeCallError, match="max_tokens"):
            complete_json(system="s", user="u", schema=SCHEMA)


def test_meter_allows_the_call_that_crosses_and_blocks_the_next(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    client = _Client(_response('{"ok": true}', output_tokens=1_000_000))
    with patch("api.llm._client", return_value=client):
        with spend_cap(5) as meter:
            complete_json(system="s", user="u", schema=SCHEMA)
            with pytest.raises(SpendCapExceeded):
                complete_json(system="s", user="u", schema=SCHEMA)
    assert meter.calls == 1
    assert meter.spent_usd == pytest.approx(20.0, abs=0.01)
    assert len(client.messages.calls) == 1


def test_web_search_tool_is_attached_when_asked(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    client = _Client(_response('{"ok": true}'))
    with patch("api.llm._client", return_value=client):
        complete_json(
            system="s", user="u", schema=SCHEMA, web_search=True, max_searches=2
        )
    tool = client.messages.calls[0]["tools"][0]
    assert tool["type"] == "web_search_20260318"
    assert tool["max_uses"] == 2


def test_batch_reserves_against_the_cap(settings):
    settings.ANTHROPIC_API_KEY = "test-key"
    settings.HYGIENE_CLAUDE_MODEL = "claude-opus-5-5"

    class _Batches:
        def __init__(self):
            self.requests = None

        def create(self, *, requests):
            self.requests = requests
            return SimpleNamespace(id="msgbatch_test")

    class _BatchClient:
        def __init__(self):
            self.messages = SimpleNamespace(batches=_Batches())

    client = _BatchClient()
    with patch("api.llm._client", return_value=client):
        with spend_cap(1) as meter:
            batch_id = submit_json_batch(
                [{"custom_id": "9", "user": "describe"}],
                system="system",
                schema=SCHEMA,
                estimate_usd_each=0.4,
            )
            with pytest.raises(SpendCapExceeded):
                submit_json_batch(
                    [
                        {"custom_id": "8", "user": "describe"},
                        {"custom_id": "7", "user": "x"},
                    ],
                    system="system",
                    schema=SCHEMA,
                    estimate_usd_each=0.4,
                )
    assert batch_id == "msgbatch_test"
    assert client.messages.batches.requests[0]["custom_id"] == "9"
    assert meter.spent_usd == pytest.approx(0.4)


def test_enrich_uses_claude_when_the_provider_is_set(settings):
    settings.HYGIENE_PROVIDER = "claude"
    payload = {
        "insufficient_evidence": False,
        "short_description": "Writes product copy for founders",
        "description": "Acme writes product copy for founders from a short brief. " * 8,
        "tags": ["Content Writing", "Text", "For Founders", "Web App"],
        "use_cases": ["Draft a homepage"],
        "features": ["Brief to draft"],
        "ideal_for": ["Founders"],
        "startup_benefits": "",
        "pricing_type": "freemium",
        "confidence": 0.7,
    }
    usage = SimpleNamespace(
        as_dict=lambda: {"prompt_tokens": 10, "completion_tokens": 5, "cost_usd": 0.02}
    )
    facts = SimpleNamespace(
        title="Acme",
        meta_description="Copy for founders",
        source_text="Acme writes product copy for startup founders.",
        pricing=None,
        stars=None,
        topics=[],
    )
    with (
        patch(
            "api.hygiene.enrich.complete_json", return_value=(payload, usage)
        ) as claude,
        patch("api.hygiene.enrich._client") as openai,
    ):
        result = enrich("Acme", "https://acme.test", facts)
    openai.assert_not_called()
    claude.assert_called_once()
    assert result["pricing_type"] == "freemium"
    assert result["usage"]["cost_usd"] == 0.02
    user_payload = json.loads(claude.call_args.kwargs["user"])
    assert "allowed_tags" not in user_payload
    assert "allowed_tags" in claude.call_args.kwargs["system"]


def test_assess_uses_claude_cost(settings):
    settings.HYGIENE_PROVIDER = "claude"
    scored = {
        cid: {"score": None, "evidence_url": None, "reasoning": ""}
        for cid in (
            "security_privacy",
            "functionality",
            "pricing_value",
            "integrations",
            "support",
            "company_stability",
            "update_frequency",
            "startup_friendliness",
        )
    }
    scored["functionality"] = {
        "score": 7,
        "evidence_url": "https://example.com",
        "reasoning": "The homepage lists the product features.",
    }
    usage = SimpleNamespace(
        as_dict=lambda: {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "cost_usd": 0.31,
        }
    )
    evidence = {
        "homepage": {"url": "https://example.com", "present": True, "text": "features"}
    }
    with patch("api.hygiene.assess.complete_json", return_value=(scored, usage)):
        result = assess("Example", "https://example.com", evidence)
    assert result["scored"]["functionality"]["score"] == 7
    assert result["usage"]["cost_usd"] == 0.31


def test_low_confidence_is_not_written():
    assert accepts_write({"insufficient_evidence": False, "confidence": 0.6}) is True
    assert accepts_write({"insufficient_evidence": False, "confidence": 0.45}) is False
    assert accepts_write({"insufficient_evidence": True, "confidence": 0.9}) is False


def test_meter_starts_empty():
    meter = SpendMeter(budget_usd=5)
    assert meter.exceeded() is False
    meter.ensure_room()
