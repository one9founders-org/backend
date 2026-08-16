"""Which *kind* of thing a directory row is.

`entry_type` (classify.py) answers "is this a real product or a listing on
someone else's platform" -- a provenance question. `track` answers a
different one: is this a hosted tool, a self-hostable repo, an agent, a
skill file, or an MCP server.

They are orthogonal on purpose. A row can be entry_type=product and
track=open_source at the same time. Track is the top-level navigation
axis, which is why it is one field with one value rather than a tag: a
founder browsing open-source repos should never be shown a SaaS product,
and tags cannot enforce that.
"""

import re

AI_TOOL = "ai_tool"
AI_AGENT = "ai_agent"
OPEN_SOURCE = "open_source"
AGENT_SKILL = "agent_skill"
MCP_SERVER = "mcp_server"

TRACK_CHOICES = [
    (AI_TOOL, "AI tool"),
    (AI_AGENT, "AI agent"),
    (OPEN_SOURCE, "Open-source repo"),
    (AGENT_SKILL, "Agent skill"),
    (MCP_SERVER, "MCP server"),
]

# Public-facing labels for the navigation, kept next to the values so the
# API and the frontend cannot drift apart.
TRACK_LABELS = {
    AI_TOOL: "AI Tools",
    AI_AGENT: "AI Agents",
    OPEN_SOURCE: "Open Source",
    AGENT_SKILL: "Agent Skills",
    MCP_SERVER: "MCP Servers",
}

CODE_HOSTS = ("github.com", "gitlab.com", "codeberg.org", "sr.ht", "bitbucket.org")

# Deliberately strict. A bare "mcp" mention means "this supports MCP",
# which most AI repos now tag themselves with -- matching on that files
# half the ecosystem as MCP servers. Require the full phrase, or the
# acronym in the project's own name.
_MCP_RE = re.compile(
    r"\bmcp[- ]servers?\b|\bmodel[- ]context[- ]protocol\b",
    re.IGNORECASE,
)
_MCP_NAME_RE = re.compile(r"\bmcp\b|[-_]mcp\b|\bmcp[-_]", re.IGNORECASE)
_SKILL_RE = re.compile(
    r"\bskill\.md\b|\bagent skills?\b|\bclaude skills?\b"
    r"|\bskills? (?:pack|library|collection)\b"
    # "Marketing skills for Claude Code and AI agents" -- the phrase that
    # matters is "skills for <an agent>", which otherwise trips the agent
    # pattern below and gets filed as an agent platform.
    r"|\bskills? for\b(?=.*\b(?:claude|agent|gpt|llm|ai)\b)",
    re.IGNORECASE,
)
# A repo literally named "<something>skills" is a skill pack.
_SKILL_NAME_RE = re.compile(r"skills?$|[-_ ]skills?\b", re.IGNORECASE)
_AGENT_RE = re.compile(
    r"\bautonomous agents?\b|\bai agents?\b|\bmulti[- ]agent\b"
    r"|\bagent(?:ic)? (?:framework|harness|runtime)\b"
    r"|\bagentic\b|\bagent swarm\b|\bself[- ]directed\b",
    re.IGNORECASE,
)
# An agent *platform* markets itself as doing work unattended.
_AGENT_BEHAVIOUR_RE = re.compile(
    r"\bruns? (?:on its own|unattended|autonomously)\b"
    r"|\bexecutes? tasks?\b|\bbrowses? the web for you\b",
    re.IGNORECASE,
)


def is_code_host(host: str) -> bool:
    host = (host or "").lower().removeprefix("www.")
    return any(host == h or host.endswith(f".{h}") for h in CODE_HOSTS)


def classify_track(
    name: str,
    website: str,
    text: str = "",
    *,
    host: str = "",
    topics: list[str] | None = None,
    has_license: bool = False,
) -> str:
    """Best-guess track for a row.

    Ordered most-specific first: a repo of Claude skills is a skill, not
    merely open source, and an MCP server is an MCP server even though it
    also lives on GitHub.
    """
    haystack = " ".join(filter(None, [name or "", text or ""]))
    topic_blob = " ".join(topics or []).lower().replace("-", " ")
    combined = f"{haystack} {topic_blob}"

    if _MCP_RE.search(combined) or _MCP_NAME_RE.search(name or ""):
        return MCP_SERVER
    if (
        _SKILL_RE.search(combined)
        or "claude skills" in topic_blob
        or _SKILL_NAME_RE.search(name or "")
    ):
        return AGENT_SKILL
    if _AGENT_RE.search(combined) or _AGENT_BEHAVIOUR_RE.search(combined):
        return AI_AGENT

    resolved_host = host or _host_of(website)
    if is_code_host(resolved_host) or has_license:
        return OPEN_SOURCE

    return AI_TOOL


def _host_of(url: str) -> str:
    if not url:
        return ""
    text = url.split("://", 1)[-1]
    return text.split("/", 1)[0].split(":")[0].lower().removeprefix("www.")


def is_free_by_construction(track: str) -> bool:
    """Tracks that cost a founder nothing but their own time.

    Used by the free-first ordering: these outrank anything with a price
    regardless of popularity.
    """
    return track in (OPEN_SOURCE, AGENT_SKILL, MCP_SERVER)
