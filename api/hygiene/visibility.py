"""Public-directory queryset: the SQL form of classify.is_publishable.

Classifying a row does not hide it on its own. Every public read path
(list, search, trending, stats, FAISS) must use publishable_queryset()
so GPT-store scrapes and confirmed-dead links stop reaching visitors.
Rows are never deleted here — they stay in the table, just not served.
"""

from django.db.models import Q

from .classify import FLAG_SENTENCE_NAME, UNPUBLISHABLE_ENTRY_TYPES, is_publishable
from .linkcheck import BROKEN, MALFORMED, PARKED, UNREACHABLE

# Confirmed-bad URLs. "unchecked" is intentionally absent: newly ingested
# rows keep the default and must remain visible until the hygiene pass
# has actually looked at them. Otherwise deploying this filter before a
# classify run would empty the directory.
UNPUBLISHABLE_LINK_STATUSES = (BROKEN, UNREACHABLE, MALFORMED, PARKED)


def row_is_publishable(tool) -> bool:
    """Same rule as publishable_q(), for a single in-memory Tool."""
    if not getattr(tool, "is_active", False):
        return False
    if tool.link_status in UNPUBLISHABLE_LINK_STATUSES:
        return False
    return is_publishable(tool.entry_type, list(tool.hygiene_flags or []))


def publishable_q() -> Q:
    """Filter matching is_publishable() plus confirmed-dead websites."""
    return (
        Q(is_active=True)
        & ~Q(entry_type__in=UNPUBLISHABLE_ENTRY_TYPES)
        & ~Q(hygiene_flags__contains=[FLAG_SENTENCE_NAME])
        & ~Q(link_status__in=UNPUBLISHABLE_LINK_STATUSES)
    )


def publishable_queryset(qs=None):
    """Active, publishable tools. Pass a queryset to layer extra filters."""
    from api.models import Tool

    if qs is None:
        qs = Tool.objects.all()
    return qs.filter(publishable_q())
