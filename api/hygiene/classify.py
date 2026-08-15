"""Segment directory rows by what they actually are.

Pure string logic -- no DB, no network -- so it stays cheap and testable.
A 2,500-row sample of production showed ~55% of rows are ChatGPT store
listings rather than products, which is the single biggest quality problem
in the directory. This module is what separates them.
"""

import re
from urllib.parse import urlparse

# Entry types, ordered roughly from "real product" to "not a product".
PRODUCT = "product"
GPT_STORE = "gpt_store"
APP_LISTING = "app_listing"
EXTENSION = "extension"
MARKETPLACE = "marketplace"
NO_URL = "no_url"

ENTRY_TYPE_CHOICES = [
    (PRODUCT, "Product"),
    (GPT_STORE, "ChatGPT store listing"),
    (APP_LISTING, "App store listing"),
    (EXTENSION, "Browser extension"),
    (MARKETPLACE, "Marketplace / template listing"),
    (NO_URL, "No website"),
]

# Hosts that mean "this row is a listing on someone else's platform",
# not a product with its own home on the web.
_HOST_TYPES = (
    (GPT_STORE, ("chat.openai.com", "chatgpt.com")),
    (
        APP_LISTING,
        ("apps.apple.com", "itunes.apple.com", "play.google.com"),
    ),
    (
        EXTENSION,
        (
            "chromewebstore.google.com",
            "chrome.google.com",
            "addons.mozilla.org",
            "microsoftedge.microsoft.com",
        ),
    ),
    (
        MARKETPLACE,
        (
            "gumroad.com",
            "lemonsqueezy.com",
            "notion.so",
            "notion.site",
            "producthunt.com",
            "workspace.google.com",
            "huggingface.co",
            "replit.com",
            "poe.com",
        ),
    ),
)

# Name-quality problems worth flagging for review.
FLAG_LEADING_PUNCT = "name_leading_punctuation"
FLAG_SENTENCE_NAME = "name_is_a_sentence"
FLAG_SEO_CRUFT = "name_has_seo_cruft"
FLAG_VERSION_SUFFIX = "name_has_version_suffix"
FLAG_TRUNCATED = "name_truncated"
FLAG_NON_ENGLISH = "name_non_english"
FLAG_OVERLONG = "name_overlong"

_SEO_CRUFT_RE = re.compile(
    r"(?:\s[|–—-]\s*(?:ai|best|free|top|the\s+#?1|\d{4})\b)"
    r"|(?:\b(?:best|top)\s+\d+\b)",
    re.IGNORECASE,
)
_VERSION_SUFFIX_RE = re.compile(r"v\d+(?:\.\d+)+\s*$", re.IGNORECASE)
_TRUNCATED_RE = re.compile(r"(?:\.{3}|…)\s*$")
_GENERIC_ROLE_RE = re.compile(
    r"^(?:expert|assistant|helper|guide|coach|tutor|advisor|mentor|specialist)\b",
    re.IGNORECASE,
)
_LATIN_EXTENDED_RE = re.compile(r"[^\x00-\x7F]")

MAX_REASONABLE_NAME_WORDS = 6
MAX_REASONABLE_NAME_CHARS = 45


def host_of(url: str) -> str:
    """Bare lowercase host, no www. Empty string when unparseable."""
    if not url:
        return ""
    candidate = url if "://" in url else f"https://{url}"
    try:
        netloc = urlparse(candidate).netloc
    except ValueError:
        return ""
    return netloc.lower().split(":")[0].removeprefix("www.")


def entry_type_for(url: str) -> str:
    """What kind of thing a row's website URL points at."""
    host = host_of(url)
    if not host:
        return NO_URL
    for entry_type, hosts in _HOST_TYPES:
        if host in hosts or any(host.endswith(f".{h}") for h in hosts):
            return entry_type
    return PRODUCT


def name_flags(name: str) -> list[str]:
    """Quality problems in a tool name, as stable flag strings."""
    text = (name or "").strip()
    flags: list[str] = []
    if not text:
        return flags

    if not text[0].isalnum():
        flags.append(FLAG_LEADING_PUNCT)
    if _TRUNCATED_RE.search(text):
        flags.append(FLAG_TRUNCATED)
    if _VERSION_SUFFIX_RE.search(text):
        flags.append(FLAG_VERSION_SUFFIX)
    if _SEO_CRUFT_RE.search(text):
        flags.append(FLAG_SEO_CRUFT)
    if _LATIN_EXTENDED_RE.search(text):
        flags.append(FLAG_NON_ENGLISH)
    if len(text) > MAX_REASONABLE_NAME_CHARS:
        flags.append(FLAG_OVERLONG)

    # "Expert in top 10 actions for success in any topic" is a prompt,
    # not a product name.
    words = text.split()
    reads_as_sentence = len(words) > MAX_REASONABLE_NAME_WORDS and (
        _GENERIC_ROLE_RE.match(text)
        or " in " in text.lower()
        or " for " in text.lower()
    )
    if reads_as_sentence:
        flags.append(FLAG_SENTENCE_NAME)

    return flags


def classify(name: str, website: str) -> tuple[str, list[str]]:
    """Return (entry_type, flags) for one directory row."""
    return entry_type_for(website), name_flags(name)


# Kept as a tuple so Django `entry_type__in=` and is_publishable() share one list.
UNPUBLISHABLE_ENTRY_TYPES = (GPT_STORE, NO_URL)


def is_publishable(entry_type: str, flags: list[str]) -> bool:
    """Whether a row belongs in the main directory as a real tool.

    Conservative on purpose: this decides visibility, never deletion.
    """
    if entry_type in UNPUBLISHABLE_ENTRY_TYPES:
        return False
    return FLAG_SENTENCE_NAME not in flags


def normalized_name(name: str) -> str:
    """Collapsed form used to spot near-duplicate rows."""
    return re.sub(r"[^a-z0-9]", "", (name or "").lower())
