"""Shared GitHub / forge discovery config (Django-free).

Partition strategy (GitHub Search hard-caps at 1,000 hits per query):
- AI/LLM topic + keyword clauses
- Star bins from 100 upward
- Auto-split any bin whose total_count >= 1000
"""

# Topics that describe AI / LLM / agent tooling founders actually use.
GITHUB_TOPICS = (
    "artificial-intelligence",
    "machine-learning",
    "deep-learning",
    "llm",
    "llms",
    "llmops",
    "llm-tools",
    "large-language-models",
    "generative-ai",
    "genai",
    "ai-agents",
    "ai-agent",
    "autonomous-agents",
    "multi-agent",
    "agentic-ai",
    "mcp",
    "mcp-server",
    "model-context-protocol",
    "rag",
    "retrieval-augmented-generation",
    "vector-database",
    "embeddings",
    "langchain",
    "llamaindex",
    "openai",
    "anthropic",
    "ollama",
    "transformers",
    "huggingface",
    "prompt-engineering",
    "ai-tools",
    "chatbot",
    "speech-to-text",
    "text-to-speech",
    "computer-vision",
    "diffusion",
    "stable-diffusion",
    "ai-code-assistant",
    "devtools",
    "developer-tools",
    "cli",
)

# Keyword fallbacks for repos that skip topics entirely.
GITHUB_KEYWORDS = (
    "llm",
    "large language model",
    "ai agent",
    "mcp server",
    "rag",
    "openai",
    "langchain",
    "ollama",
    "generative ai",
    "transformer model",
)

# Inclusive star bins. Start at 100+ as requested. Dense low bins are narrow
# so a single topic×bin query stays under the 1,000-result Search API cap.
GITHUB_STAR_BINS = (
    (100, 119),
    (120, 149),
    (150, 199),
    (200, 299),
    (300, 499),
    (500, 999),
    (1000, 2499),
    (2500, 9999),
    (10000, None),  # open-ended high bin
)

# Minimum stars for admission into the OSS directory.
MIN_OSS_STARS = 100

# Legacy flat queries kept for scrapers / smoke tests; discovery prefers
# topic × star-bin expansion via ``iter_github_search_queries``.
GITHUB_STAR_QUERIES = tuple(
    f"topic:{topic} stars:>={MIN_OSS_STARS} fork:false archived:false"
    for topic in (
        "llm-tools",
        "ai-agents",
        "mcp-server",
        "model-context-protocol",
        "rag",
        "generative-ai",
        "llm",
    )
) + (
    f"mcp server in:name,description stars:>={MIN_OSS_STARS} fork:false",
    f"browser automation ai stars:>={MIN_OSS_STARS} fork:false",
    "reticle in:name,description fork:false",
)

GITHUB_SEED_REPOS = (
    "reticlehq/reticle",
    "browser-use/browser-use",
    "microsoft/playwright-mcp",
    "modelcontextprotocol/servers",
    "langchain-ai/langchain",
    "vercel/ai",
    "huggingface/transformers",
    "ggerganov/llama.cpp",
    "ollama/ollama",
    "open-webui/open-webui",
    "Aider-AI/aider",
    "continuedev/continue",
    "crewAIInc/crewAI",
    "OpenHands/OpenHands",
    "BerriAI/litellm",
    "n8n-io/n8n",
    "comfyanonymous/ComfyUI",
    "TabbyML/tabby",
)

# Search API returns at most 1,000 matches; probe/split above this.
GITHUB_SEARCH_RESULT_CAP = 1000
# Throttle authenticated search (~30 req/min).
GITHUB_SEARCH_MIN_INTERVAL_SEC = 2.1


def star_clause(lo: int, hi: int | None) -> str:
    if hi is None:
        return f"stars:>={lo}"
    return f"stars:{lo}..{hi}"


def split_star_bin(lo: int, hi: int | None) -> list[tuple[int, int | None]]:
    """Bisect a star bin when Search reports total_count >= 1000."""
    if hi is None:
        # Open-ended: peel off a finite upper window, keep a higher open bin.
        mid = max(lo + 1, lo * 2)
        return [(lo, mid - 1), (mid, None)]
    if hi <= lo:
        return [(lo, hi)]
    mid = (lo + hi) // 2
    if mid <= lo:
        return [(lo, hi)]
    return [(lo, mid), (mid + 1, hi)]


def iter_base_github_queries() -> list[tuple[str, int, int | None]]:
    """Return (qualifier, star_lo, star_hi) before auto-split.

    ``qualifier`` is everything except the stars: clause (topic or keyword).
    """
    rows: list[tuple[str, int, int | None]] = []
    for topic in GITHUB_TOPICS:
        for lo, hi in GITHUB_STAR_BINS:
            rows.append((f"topic:{topic} fork:false archived:false", lo, hi))
    for keyword in GITHUB_KEYWORDS:
        for lo, hi in GITHUB_STAR_BINS:
            rows.append(
                (
                    f"{keyword} in:name,description fork:false archived:false",
                    lo,
                    hi,
                )
            )
    return rows
