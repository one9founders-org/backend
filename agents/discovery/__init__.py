"""Discover and refresh AI agents from public catalogs."""

ALL_SOURCES = (
    "aiagentsdirectory",
    "enterprisedna",
    "awesome",
    "github",
    "huggingface",
    "producthunt",
    "hackernews",
)

SOURCE_RANK = {
    "aiagentsdirectory": 100,
    "enterprisedna": 80,
    "awesome": 70,
    "github": 50,
    "huggingface": 40,
    "producthunt": 30,
    "hackernews": 20,
}
