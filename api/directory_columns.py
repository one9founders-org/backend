"""Two-column directory payload for the website.

Founders need a clear split: paid/hosted AI tools vs free open-source
GitHub repos they can install. The frontend should call
``GET /api/tools/directory-columns/`` and render ``columns`` as two
lanes. Each column already includes the filter query to page more rows.
"""

from django.db.models import Count

from api.hygiene.track import (
    AI_TOOL,
    OPEN_SOURCE,
    TRACK_LABELS,
)
from api.hygiene.visibility import publishable_queryset
from api.serializers import ToolListSerializer

# Primary navigation columns for the public directory.
DIRECTORY_COLUMNS = (
    {
        "id": "ai_tools",
        "track": AI_TOOL,
        "label": TRACK_LABELS[AI_TOOL],
        "blurb": "Hosted AI products you can sign up for today.",
        "list_path": "/api/tools/?track=ai_tool",
    },
    {
        "id": "open_source",
        "track": OPEN_SOURCE,
        "label": TRACK_LABELS[OPEN_SOURCE],
        "blurb": "GitHub open-source repos you can install for free.",
        "list_path": "/api/tools/?track=open_source",
    },
)

DEFAULT_PER_COLUMN = 12


def build_directory_columns(*, per_column: int = DEFAULT_PER_COLUMN) -> dict:
    qs = publishable_queryset()
    counts = {
        row["track"]: row["count"]
        for row in qs.values("track").annotate(count=Count("id"))
    }

    columns = []
    for spec in DIRECTORY_COLUMNS:
        track = spec["track"]
        tools = list(
            qs.filter(track=track)
            .prefetch_related("categories")
            .order_by("-is_featured", "-popularity_score", "-rating", "name")[
                :per_column
            ]
        )
        columns.append(
            {
                **spec,
                "label": TRACK_LABELS.get(track, spec["label"]),
                "count": counts.get(track, 0),
                "tools": ToolListSerializer(tools, many=True).data,
            }
        )

    return {
        "columns": columns,
        "tracks": [
            {"track": key, "label": label} for key, label in TRACK_LABELS.items()
        ],
        "per_column": per_column,
    }
