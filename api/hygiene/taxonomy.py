"""A faceted, controlled tag vocabulary for the tool directory.

The live directory has 81 loose tags and 93% of rows carry none, so tags
are useless for filtering today. This replaces that with five orthogonal
facets, each drawn from a closed list, so a tool ends up with broad,
predictable tags instead of one narrow accidental label.

Facets are deliberately orthogonal: a tool gets tags from several of them,
which is what makes cross-cutting filters ("free video tools with an API")
possible.
"""

FUNCTION = "function"
AUDIENCE = "audience"
MODALITY = "modality"
DEPLOYMENT = "deployment"
PRICING = "pricing"

FACETS = (FUNCTION, AUDIENCE, MODALITY, DEPLOYMENT, PRICING)

# tag -> (facet, matching keywords). Keywords drive deterministic inference
# from a tool's own text before any LLM call is made.
VOCABULARY: dict[str, tuple[str, tuple[str, ...]]] = {
    # ---- What job the tool does -------------------------------------
    "Content Writing": (FUNCTION, ("copywriting", "blog post", "article writer")),
    "Copy Editing": (FUNCTION, ("proofread", "grammar", "rewrite", "paraphras")),
    "Translation": (FUNCTION, ("translate", "translation", "localiz")),
    "Summarization": (FUNCTION, ("summar", "tl;dr", "digest")),
    "Search & Retrieval": (FUNCTION, ("semantic search", "rag", "vector search")),
    "Research": (FUNCTION, ("research", "literature", "citation")),
    "Data Analysis": (FUNCTION, ("analytics", "dashboard", "data analysis", "bi tool")),
    "Automation": (FUNCTION, ("automat", "workflow", "zapier", "no-code bot")),
    "Agents": (FUNCTION, ("autonomous agent", "ai agent", "multi-agent")),
    "Chat Assistant": (FUNCTION, ("chatbot", "assistant", "conversational")),
    "Customer Support": (FUNCTION, ("helpdesk", "support ticket", "live chat")),
    "Sales & CRM": (FUNCTION, ("crm", "sales pipeline", "lead gen", "prospect")),
    "Marketing": (FUNCTION, ("marketing", "campaign", "ad copy", "advertis")),
    "SEO": (FUNCTION, ("seo", "search engine optim", "backlink", "serp")),
    "Social Media": (FUNCTION, ("social media", "instagram", "linkedin post")),
    "Email": (FUNCTION, ("email", "newsletter", "inbox", "cold outreach")),
    "Design": (FUNCTION, ("design", "mockup", "wireframe", "ui kit")),
    "Image Generation": (FUNCTION, ("image gener", "text-to-image", "art gener")),
    "Image Editing": (FUNCTION, ("background remov", "upscal", "retouch", "inpaint")),
    "Video Generation": (FUNCTION, ("video gener", "text-to-video", "avatar video")),
    "Video Editing": (FUNCTION, ("video edit", "subtitle", "caption", "clip")),
    "Audio & Speech": (
        FUNCTION,
        ("text-to-speech", "voice clon", "transcri", "podcast"),
    ),
    "Music": (FUNCTION, ("music gener", "compose", "soundtrack")),
    "Code Generation": (FUNCTION, ("code gener", "copilot", "autocomplete code")),
    "Code Review": (FUNCTION, ("code review", "static analysis", "linting")),
    "Testing & QA": (FUNCTION, ("test automation", "qa", "end-to-end test")),
    "DevOps": (FUNCTION, ("ci/cd", "deployment", "infrastructure", "observability")),
    "Security": (FUNCTION, ("security", "vulnerabilit", "penetration", "compliance")),
    "Productivity": (FUNCTION, ("note-taking", "task manage", "calendar", "meeting")),
    "Project Management": (FUNCTION, ("project manage", "kanban", "sprint", "roadmap")),
    "Knowledge Management": (FUNCTION, ("wiki", "knowledge base", "second brain")),
    "Document Processing": (FUNCTION, ("pdf", "ocr", "document extract", "invoice")),
    "Presentations": (FUNCTION, ("slide", "presentation", "deck", "pitch deck")),
    "Spreadsheets": (FUNCTION, ("spreadsheet", "excel", "google sheets")),
    "Recruiting & HR": (FUNCTION, ("recruit", "resume", "applicant", "onboarding")),
    "Legal": (FUNCTION, ("legal", "contract", "nda", "terms of service")),
    "Finance & Accounting": (FUNCTION, ("invoic", "bookkeep", "accounting", "payroll")),
    "Education & Training": (FUNCTION, ("course", "tutor", "learning", "quiz")),
    "Healthcare": (FUNCTION, ("clinical", "patient", "medical", "diagnos")),
    "E-commerce": (FUNCTION, ("shopify", "product listing", "storefront", "dropship")),
    "Real Estate": (FUNCTION, ("real estate", "property listing")),
    "Gaming": (FUNCTION, ("game dev", "npc", "unity", "unreal")),
    "3D & CAD": (FUNCTION, ("3d model", "cad", "render", "blender")),
    "Model Hosting": (FUNCTION, ("inference api", "model hosting", "fine-tun")),
    "Prompt Engineering": (FUNCTION, ("prompt", "prompt library", "prompt manage")),
    # ---- Who it is for ----------------------------------------------
    "For Founders": (AUDIENCE, ("founder", "startup", "solo founder")),
    "For Developers": (AUDIENCE, ("developer", "engineer", "api-first", "sdk")),
    "For Designers": (AUDIENCE, ("designer", "creative team")),
    "For Marketers": (AUDIENCE, ("marketer", "growth team", "demand gen")),
    "For Sales Teams": (AUDIENCE, ("sales team", "account executive", "sdr")),
    "For Educators": (AUDIENCE, ("teacher", "educator", "classroom", "student")),
    "For Enterprises": (AUDIENCE, ("enterprise", "sso", "soc 2", "on-premise")),
    "For Small Business": (AUDIENCE, ("small business", "smb", "freelanc", "agency")),
    "For Creators": (AUDIENCE, ("creator", "influencer", "youtuber", "streamer")),
    "For Researchers": (AUDIENCE, ("researcher", "academic", "scientist")),
    # ---- What it operates on ----------------------------------------
    "Text": (MODALITY, ("text", "writing", "language model")),
    "Image": (MODALITY, ("image", "photo", "picture", "visual")),
    "Video": (MODALITY, ("video", "footage", "film")),
    "Audio": (MODALITY, ("audio", "voice", "speech", "sound")),
    "Code": (MODALITY, ("code", "programming", "repository")),
    "Structured Data": (MODALITY, ("csv", "database", "sql", "tabular")),
    "Multimodal": (MODALITY, ("multimodal", "vision-language")),
    # ---- How you use it ----------------------------------------------
    "Web App": (DEPLOYMENT, ("web app", "browser-based", "web-based")),
    "API": (DEPLOYMENT, ("api", "rest api", "endpoint", "developer api")),
    "Browser Extension": (DEPLOYMENT, ("chrome extension", "browser extension")),
    "Desktop App": (DEPLOYMENT, ("desktop app", "macos app", "windows app")),
    "Mobile App": (DEPLOYMENT, ("ios app", "android app", "mobile app")),
    "CLI": (DEPLOYMENT, ("command line", "cli", "terminal")),
    "Self-Hosted": (DEPLOYMENT, ("self-host", "on-premise", "docker")),
    "Open Source": (DEPLOYMENT, ("open source", "github", "mit license", "apache")),
    "Plugin / Integration": (DEPLOYMENT, ("plugin", "integration", "add-on")),
    # ---- Pricing posture ---------------------------------------------
    "Free": (PRICING, ("free forever", "completely free", "no cost")),
    "Freemium": (PRICING, ("freemium", "free plan", "free tier")),
    "Free Trial": (PRICING, ("free trial", "trial period")),
    "Paid": (PRICING, ("subscription", "per month", "paid plan")),
    "Usage-Based": (PRICING, ("pay as you go", "per token", "usage-based", "credits")),
    "Enterprise Pricing": (PRICING, ("contact sales", "custom pricing", "quote")),
}

# Old loose tags seen in production -> new canonical tags.
# Anything not listed here is dropped during the revision pass.
LEGACY_TAG_MAP: dict[str, list[str]] = {
    "assistant": ["Chat Assistant"],
    "chatbot": ["Chat Assistant"],
    "communication": ["Chat Assistant"],
    "automation": ["Automation"],
    "productivity": ["Productivity"],
    "copywriting": ["Content Writing", "Text"],
    "writing": ["Content Writing", "Text"],
    "social networks": ["Social Media"],
    "social media": ["Social Media"],
    "video": ["Video"],
    "images": ["Image"],
    "image": ["Image"],
    "audio": ["Audio"],
    "music": ["Music", "Audio"],
    "data analysis": ["Data Analysis", "Structured Data"],
    "seo": ["SEO"],
    "marketing": ["Marketing"],
    "design": ["Design"],
    "code": ["Code Generation", "Code"],
    "developer": ["For Developers"],
    "education": ["Education & Training"],
    "finance": ["Finance & Accounting"],
    "legal": ["Legal"],
    "hr": ["Recruiting & HR"],
    "sales": ["Sales & CRM"],
    "research": ["Research"],
    "3d": ["3D & CAD"],
    "voice": ["Audio & Speech", "Audio"],
    "startup": ["For Founders"],
    "enterprise": ["For Enterprises"],
    "freelance": ["For Small Business"],
    "agency": ["For Small Business"],
    "entrepreneur": ["For Founders"],
    "e-merchant": ["E-commerce"],
    "teacher": ["For Educators"],
    "saas": ["Web App"],
}

ALL_TAGS = tuple(sorted(VOCABULARY))
TAGS_BY_FACET: dict[str, tuple[str, ...]] = {
    facet: tuple(sorted(t for t, (f, _kw) in VOCABULARY.items() if f == facet))
    for facet in FACETS
}


def facet_of(tag: str) -> str | None:
    entry = VOCABULARY.get(tag)
    return entry[0] if entry else None


def is_valid(tag: str) -> bool:
    return tag in VOCABULARY


def migrate_legacy_tags(tags: list[str]) -> list[str]:
    """Map a row's existing loose tags onto the controlled vocabulary."""
    out: list[str] = []
    for raw in tags or []:
        key = (raw or "").strip().lower()
        if not key:
            continue
        if raw in VOCABULARY:
            out.append(raw)
            continue
        out.extend(LEGACY_TAG_MAP.get(key, []))
    return dedupe(out)


def infer_tags(text: str, limit: int = 12) -> list[str]:
    """Keyword-match a tool's own text against the vocabulary.

    Cheap first pass -- it resolves most rows without an LLM call, and gives
    the LLM a grounded starting point for the rest.
    """
    haystack = (text or "").lower()
    if not haystack.strip():
        return []
    hits: list[tuple[int, str]] = []
    for tag, (_facet, keywords) in VOCABULARY.items():
        score = sum(1 for kw in keywords if kw in haystack)
        if score:
            hits.append((score, tag))
    hits.sort(key=lambda pair: (-pair[0], pair[1]))
    return [tag for _score, tag in hits[:limit]]


def dedupe(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        if tag in VOCABULARY and tag not in seen:
            seen.add(tag)
            out.append(tag)
    return out


def balance(tags: list[str], max_per_facet: int = 4) -> list[str]:
    """Cap any single facet so tags stay broad rather than lopsided."""
    counts: dict[str, int] = {}
    out: list[str] = []
    for tag in dedupe(tags):
        facet = facet_of(tag)
        if facet is None:
            continue
        if counts.get(facet, 0) >= max_per_facet:
            continue
        counts[facet] = counts.get(facet, 0) + 1
        out.append(tag)
    return out
