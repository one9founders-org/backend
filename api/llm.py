"""Claude client for directory hygiene.

OpenAI stays the default. Set HYGIENE_PROVIDER=claude to send
hygiene enrichment and assessment through this module.

Pricing is Claude Opus 5.5 on the Claude API (checked 16 Oct 2026):
$4 / $20 per million input / output tokens, 5-minute cache writes at
$5, cache reads at $0.20, batch token rates at half, web search at
$10 per 1,000 searches. Unknown model ids are priced as Opus 5.5 so a
typo cannot under-count the cap.
"""

from __future__ import annotations

import json
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-opus-5-5"
EFFORTS = ("low", "medium", "high", "xhigh", "max")

# input, output, 5-minute cache write, cache read — USD per million tokens.
_OPUS_55_RATES = (4.0, 20.0, 5.0, 0.20)
REALTIME_RATES = {
    DEFAULT_MODEL: _OPUS_55_RATES,
}
WEB_SEARCH_USD = 10.0 / 1000.0
BATCH_TOKEN_SCALE = 0.5

_METER: ContextVar["SpendMeter | None"] = ContextVar("claude_spend_meter", default=None)


class LLMError(Exception):
    pass


class SpendCapExceeded(LLMError):
    def __init__(self, spent: float, budget: float):
        self.spent = spent
        self.budget = budget
        super().__init__(
            f"spend ${spent:.4f} reached cap ${budget:.2f}; no further Claude calls"
        )


class ClaudeCallError(LLMError):
    """API failure, refusal, or a reply cut off by max_tokens."""

    def __init__(self, message: str, usage: "CallUsage | None" = None):
        super().__init__(message)
        self.usage = usage


def provider_name() -> str:
    raw = getattr(settings, "HYGIENE_PROVIDER", "openai") or "openai"
    return str(raw).strip().lower()


def provider_is_claude() -> bool:
    return provider_name() == "claude"


def model_name() -> str:
    raw = getattr(settings, "HYGIENE_CLAUDE_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL
    return str(raw).strip() or DEFAULT_MODEL


def effort_name(override: str | None = None) -> str:
    raw = (
        override
        if override is not None
        else getattr(settings, "HYGIENE_CLAUDE_EFFORT", "medium")
    )
    value = str(raw or "medium").strip().lower()
    if value not in EFFORTS:
        logger.warning("Unknown Claude effort %r; using medium", raw)
        return "medium"
    return value


def token_cost_usd(
    *,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
    cache_read_input_tokens: int = 0,
    web_search_requests: int = 0,
    model: str = DEFAULT_MODEL,
    batch: bool = False,
) -> float:
    rates = REALTIME_RATES.get(model)
    if rates is None:
        logger.warning("Unknown Claude model %s; pricing as %s", model, DEFAULT_MODEL)
        rates = _OPUS_55_RATES
    scale = BATCH_TOKEN_SCALE if batch else 1.0
    input_rate, output_rate, write_rate, read_rate = (rate * scale for rate in rates)
    tokens = (
        input_tokens * input_rate
        + output_tokens * output_rate
        + cache_creation_input_tokens * write_rate
        + cache_read_input_tokens * read_rate
    ) / 1_000_000
    return tokens + web_search_requests * WEB_SEARCH_USD


@dataclass
class CallUsage:
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    web_search_requests: int = 0
    cost_usd: float = 0.0
    stop_reason: str = ""
    batch: bool = False

    def as_dict(self) -> dict:
        # prompt_tokens includes cache tokens so logs show the whole input.
        # cost_usd is the billed amount; do not reprice prompt_tokens.
        prompt = (
            self.input_tokens
            + self.cache_creation_input_tokens
            + self.cache_read_input_tokens
        )
        return {
            "model": self.model,
            "prompt_tokens": prompt,
            "completion_tokens": self.output_tokens,
            "input_tokens": self.input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "web_search_requests": self.web_search_requests,
            "cost_usd": round(self.cost_usd, 6),
            "stop_reason": self.stop_reason,
            "batch": self.batch,
        }


@dataclass
class SpendMeter:
    """Hard dollar cap for one workstream. The call that crosses the cap
    is already spent; the next call is refused."""

    budget_usd: float
    spent_usd: float = 0.0
    calls: int = 0
    notes: list[str] = field(default_factory=list)

    def exceeded(self) -> bool:
        return self.spent_usd >= self.budget_usd

    def ensure_room(self) -> None:
        if self.exceeded():
            raise SpendCapExceeded(self.spent_usd, self.budget_usd)

    def charge(self, usage: CallUsage) -> None:
        self.spent_usd += float(usage.cost_usd or 0)
        self.calls += 1

    def charge_usd(self, amount: float, note: str = "") -> None:
        self.spent_usd += float(amount or 0)
        self.calls += 1
        if note:
            self.notes.append(note)


@contextmanager
def spend_cap(budget_usd: float | None):
    """Bind a meter for Claude calls on this thread. None disables the cap."""
    if budget_usd is None:
        yield None
        return
    meter = SpendMeter(budget_usd=float(budget_usd))
    token = _METER.set(meter)
    try:
        yield meter
    finally:
        _METER.reset(token)


def _client():
    import anthropic

    key = getattr(settings, "ANTHROPIC_API_KEY", "") or ""
    if not str(key).strip():
        raise ClaudeCallError("ANTHROPIC_API_KEY is not set")
    return anthropic.Anthropic(api_key=key)


def _usage_int(usage, name: str) -> int:
    if usage is None:
        return 0
    if isinstance(usage, dict):
        value = usage.get(name, 0)
    else:
        value = getattr(usage, name, 0)
    return int(value or 0)


def _web_searches(usage) -> int:
    if usage is None:
        return 0
    raw = (
        usage.get("server_tool_use")
        if isinstance(usage, dict)
        else getattr(usage, "server_tool_use", None)
    )
    if raw is None:
        return 0
    if isinstance(raw, dict):
        return int(raw.get("web_search_requests") or 0)
    return int(getattr(raw, "web_search_requests", 0) or 0)


def usage_from_response(response, *, model: str, batch: bool = False) -> CallUsage:
    usage = getattr(response, "usage", None)
    parsed = CallUsage(
        model=model,
        input_tokens=_usage_int(usage, "input_tokens"),
        output_tokens=_usage_int(usage, "output_tokens"),
        cache_creation_input_tokens=_usage_int(usage, "cache_creation_input_tokens"),
        cache_read_input_tokens=_usage_int(usage, "cache_read_input_tokens"),
        web_search_requests=_web_searches(usage),
        stop_reason=str(getattr(response, "stop_reason", "") or ""),
        batch=batch,
    )
    parsed.cost_usd = token_cost_usd(
        input_tokens=parsed.input_tokens,
        output_tokens=parsed.output_tokens,
        cache_creation_input_tokens=parsed.cache_creation_input_tokens,
        cache_read_input_tokens=parsed.cache_read_input_tokens,
        web_search_requests=parsed.web_search_requests,
        model=model,
        batch=batch,
    )
    return parsed


def _system_blocks(text: str) -> list[dict]:
    block: dict = {"type": "text", "text": text}
    # Short prompts are rejected by prompt caching. Long shared prompts
    # (system text plus the tag list or schema notes) are cached.
    if len(text) >= 2000:
        block["cache_control"] = {"type": "ephemeral"}
    return [block]


def _without_cache(kwargs: dict) -> dict:
    system = kwargs.get("system")
    if not isinstance(system, list):
        return kwargs
    cleaned = []
    for block in system:
        if isinstance(block, dict):
            cleaned.append(
                {key: value for key, value in block.items() if key != "cache_control"}
            )
        else:
            cleaned.append(block)
    return {**kwargs, "system": cleaned}


def _response_text(response) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", None) or []:
        kind = getattr(block, "type", None)
        if kind is None and isinstance(block, dict):
            kind = block.get("type")
        if kind != "text":
            continue
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(text)
    return "".join(parts).strip()


def _create(client, kwargs: dict):
    import anthropic

    try:
        return client.messages.create(**kwargs)
    except anthropic.BadRequestError as exc:
        message = str(exc).lower()
        if "cache" in message and kwargs.get("system"):
            logger.info("Claude rejected prompt cache; retrying without it")
            return client.messages.create(**_without_cache(kwargs))
        raise ClaudeCallError(str(exc)) from exc
    except anthropic.APIError as exc:
        raise ClaudeCallError(str(exc)) from exc


def complete_json(
    *,
    system: str,
    user: str,
    schema: dict,
    max_tokens: int = 8192,
    effort: str | None = None,
    model: str | None = None,
    web_search: bool = False,
    max_searches: int = 3,
) -> tuple[dict, CallUsage]:
    """One realtime Claude call that must return schema-valid JSON.

    Raises SpendCapExceeded before the request when the active meter is
    already over budget. Raises ClaudeCallError on refusal, truncation,
    or an API error. Failed rows must not be written.
    """
    meter = _METER.get()
    if meter is not None:
        meter.ensure_room()

    chosen_model = model or model_name()
    chosen_effort = effort_name(effort)
    kwargs: dict = {
        "model": chosen_model,
        "max_tokens": max_tokens,
        "system": _system_blocks(system),
        "messages": [{"role": "user", "content": user}],
        "output_config": {
            "effort": chosen_effort,
            "format": {"type": "json_schema", "schema": schema},
        },
    }
    if web_search:
        kwargs["tools"] = [
            {
                "type": "web_search_20260318",
                "name": "web_search",
                "max_uses": max(1, int(max_searches)),
            }
        ]

    response = _create(_client(), kwargs)
    usage = usage_from_response(response, model=chosen_model, batch=False)
    if meter is not None:
        meter.charge(usage)
    logger.info(
        "claude model=%s effort=%s stop=%s in=%s out=%s cache_read=%s "
        "cache_write=%s searches=%s cost=$%.4f",
        chosen_model,
        chosen_effort,
        usage.stop_reason,
        usage.input_tokens,
        usage.output_tokens,
        usage.cache_read_input_tokens,
        usage.cache_creation_input_tokens,
        usage.web_search_requests,
        usage.cost_usd,
    )

    if usage.stop_reason == "refusal":
        raise ClaudeCallError("Claude refused the request", usage)
    if usage.stop_reason == "max_tokens":
        raise ClaudeCallError("Claude hit max_tokens before finishing JSON", usage)

    raw = _response_text(response)
    if not raw:
        raise ClaudeCallError(
            f"Claude returned no JSON (stop={usage.stop_reason})", usage
        )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ClaudeCallError("Claude returned invalid JSON", usage) from exc
    if not isinstance(data, dict):
        raise ClaudeCallError("Claude JSON was not an object", usage)
    return data, usage


def submit_json_batch(
    items: list[dict],
    *,
    system: str,
    schema: dict,
    max_tokens: int = 8192,
    effort: str | None = None,
    estimate_usd_each: float = 0.05,
) -> str:
    """Submit a Message Batch. custom_id on each item is the tool id.

    Reserves estimate_usd_each against the active meter before submit so
    a second batch cannot slip past the cap. Reconcile the reservation
    with real usage when the batch results come back. Returns the batch id.
    """
    if not items:
        raise ClaudeCallError("batch has no requests")
    meter = _METER.get()
    estimate = estimate_usd_each * len(items)
    if meter is not None:
        meter.ensure_room()
        if meter.spent_usd + estimate > meter.budget_usd:
            raise SpendCapExceeded(meter.spent_usd + estimate, meter.budget_usd)

    chosen_effort = effort_name(effort)
    system_blocks = _system_blocks(system)
    requests = []
    for item in items:
        custom_id = str(item["custom_id"])
        requests.append(
            {
                "custom_id": custom_id,
                "params": {
                    "model": model_name(),
                    "max_tokens": max_tokens,
                    "system": system_blocks,
                    "messages": [{"role": "user", "content": item["user"]}],
                    "output_config": {
                        "effort": chosen_effort,
                        "format": {"type": "json_schema", "schema": schema},
                    },
                },
            }
        )
    batch = _client().messages.batches.create(requests=requests)
    batch_id = str(getattr(batch, "id", "") or "")
    if not batch_id:
        raise ClaudeCallError("Claude batch response had no id")
    if meter is not None:
        meter.charge_usd(estimate, note=f"batch {batch_id} reserved ${estimate:.2f}")
    logger.info(
        "claude batch %s requests=%s reserved=$%.2f", batch_id, len(items), estimate
    )
    return batch_id
