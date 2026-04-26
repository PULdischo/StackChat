"""Canonical search-field tokens, facet names, and sort mappings for the
Princeton University Library Blacklight catalog.

Verified against the live catalog UI at catalog.princeton.edu/help and /advanced.
"""

from __future__ import annotations

# ── Search fields ─────────────────────────────────────────────────────────────

#: Maps the Blacklight ``search_field=`` token to a human-readable label.
#: Used for validation and for building fixture tests.
SEARCH_FIELDS: dict[str, str] = {
    "all_fields": "Keyword (default)",
    "title": "Title (keyword)",
    "author": "Author (keyword)",
    "subject": "Subject (keyword)",
    "left_anchor": "Title starts with",
    "series_title": "Series title",
    "publisher": "Publisher",
    "notes": "Notes",
    "isbn": "ISBN",
    "issn": "ISSN",
}

# ── Facet fields ──────────────────────────────────────────────────────────────

#: Facet field names as they appear in Blacklight's JSON response and in
#: ``f[FIELD][]=`` filter parameters.
FACET_FIELDS: list[str] = [
    "format",
    "language_facet",
    "author_s",
    "subject_topic_facet",
    "subject_era_facet",
    "subject_geo_facet",
    "pub_date_start_sort",
    "location",
    "advanced_location_s",
    "access_facet",
    "recently_added_facet",
]

#: Facet fields surfaced in every search response (compact subset).
DEFAULT_RESPONSE_FACETS: list[str] = [
    "format",
    "language_facet",
    "location",
    "access_facet",
]

# ── Sort options ──────────────────────────────────────────────────────────────

#: Maps the friendly sort token accepted by tools to the raw Blacklight sort
#: string sent to the API.
SORT_MAP: dict[str, str] = {
    "relevance": "score desc, pub_date_start_sort desc, title_sort asc",
    "newest": "pub_date_sort desc",
    "oldest": "pub_date_sort asc",
    "title_asc": "title_sort asc",
    "title_desc": "title_sort desc",
    "author_asc": "author_sort asc",
}

SortLiteral = str  # "relevance" | "newest" | "oldest" | "title_asc" | "title_desc" | "author_asc"

# ── Browse indexes ────────────────────────────────────────────────────────────

BROWSE_INDEXES: dict[str, str] = {
    "names": "/browse/names.json",
    "subjects": "/browse/subjects.json",
    "call_numbers": "/browse/call_numbers.json",
}

# ── Access facet values ───────────────────────────────────────────────────────

ACCESS_ONLINE = "Online"
ACCESS_IN_LIBRARY = "In the Library"
