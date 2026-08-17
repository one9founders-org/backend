# Tunables for the directory hygiene pass.
# Nothing in this package writes to the database unless a command is run
# with --apply. Every write is recorded to a reversible JSON log.

# Link checking
LINK_TIMEOUT = 12
LINK_RETRIES = 1
# Hosts that rate-limit aggressively; checked with a slower cadence.
LINK_SLOW_HOSTS = frozenset({"apps.apple.com", "play.google.com"})

# Logo resolution
LOGO_MIN_BYTES = 512
LOGO_TIMEOUT = 10

# Enrichment
TARGET_SHORT_DESCRIPTION_WORDS = (8, 18)
TARGET_DESCRIPTION_WORDS = (55, 110)
MIN_TAGS = 4
MAX_TAGS = 12

# Popularity ranking: weights must sum to 1.0.
RANK_WEIGHTS = {
    "external": 0.45,  # third-party review counts / stars / directory presence
    "search": 0.25,  # search-result footprint for the tool name
    "engagement": 0.20,  # first-party clicks and views
    "completeness": 0.10,  # how well-formed the record is
}

# A tool is only eligible for homepage/featured surfaces above this score.
RANK_FEATURE_THRESHOLD = 0.55

# Published-evidence assessment (api/hygiene/evidence.py, assess.py).
EVIDENCE_TIMEOUT = 8
EVIDENCE_MAX_FETCHES = 6
EVIDENCE_TEXT_LIMIT = 2500
# Parse this many HTML characters at most. Larger slices OOM the web
# container (BeautifulSoup + gunicorn) and kill the overnight pass.
EVIDENCE_HTML_LIMIT = 40_000
ASSESS_BUDGET_CEILING_USD = 50.0
ASSESS_DEFAULT_BUDGET_USD = 40.0
