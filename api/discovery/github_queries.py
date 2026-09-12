"""Shared GitHub Search queries for OSS tool discovery (Django-free).

Used by ``api.discovery.sources`` and ``scrapers.github`` so star thresholds
and curated seeds stay in one place.
"""

# Topic search stays free (GitHub API). Prefer recently *pushed* repos so
# established projects keep showing up; a created-only window misses them.
GITHUB_TOPICS = (
    "artificial-intelligence",
    "llm-tools",
    "llm",
    "generative-ai",
    "ai-agents",
    "mcp-server",
    "model-context-protocol",
    "rag",
    "langchain",
    "developer-tools",
    "devtools",
    "cli",
)

# Most-starred *user-facing* OSS tools (no date window). Sorted by stars
# via the Search API. Thresholds keep noise down without needing Firecrawl.
# Pattern mirrors agents/discovery GITHUB_QUERIES (topic + stars + fork:false).
GITHUB_STAR_QUERIES = (
    "topic:llm-tools stars:>=100 fork:false",
    "topic:ai-agents stars:>=100 fork:false",
    "topic:mcp-server stars:>=50 fork:false",
    "topic:model-context-protocol stars:>=50 fork:false",
    "topic:developer-tools stars:>=200 fork:false",
    "topic:devtools stars:>=200 fork:false",
    "topic:rag stars:>=100 fork:false",
    "topic:generative-ai stars:>=200 fork:false",
    "topic:llm stars:>=500 fork:false",
    "mcp server in:name,description stars:>=50 fork:false",
    "browser automation ai stars:>=100 fork:false",
    "reticle in:name,description fork:false",
)

# Always consider these high-signal open-source repos even when they are
# older than the search window (deduped against search hits).
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
