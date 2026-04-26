"""Normalize Solr/Blacklight field names to the clean tool-facing schema.

Blacklight exposes many suffixed field variants (``*_display``, ``*_facet``,
``*_tsim``, ``*_s``, etc.).  This module maps them to human-friendly names.

Real response quirk: many attribute values are wrapped in a JSON:API
``document_value`` object:
    {"type": "document_value", "attributes": {"value": <actual>, "label": "…"}}

The ``_unwrap`` helper extracts the inner value transparently.
"""

from __future__ import annotations

from typing import Any

from stackchat.models import BrowseEntry, FacetValue, RecordResponse, SearchResult

# ── Field-value unwrapping ────────────────────────────────────────────────────


def _unwrap(value: Any) -> Any:
    """Unwrap a Blacklight ``document_value`` envelope if present.

    Blacklight wraps most display fields in::

        {"type": "document_value", "attributes": {"value": <actual>}}

    Returns the inner ``value`` (or the original *value* if it's not wrapped).
    """
    if isinstance(value, dict) and value.get("type") == "document_value":
        return value.get("attributes", {}).get("value")
    return value


def _first(value: Any) -> str | None:
    """Unwrap, then return the first element if it's a list."""
    raw = _unwrap(value)
    if isinstance(raw, list):
        return str(raw[0]) if raw else None
    return str(raw) if raw else None


def _listify(value: Any) -> list[str]:
    """Unwrap, then ensure the result is a list of strings."""
    raw = _unwrap(value)
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(v) for v in raw]
    return [str(raw)]


def normalize_doc(doc: dict[str, Any]) -> SearchResult:
    """Convert one Blacklight JSON:API document node to a :class:`SearchResult`."""
    attrs: dict[str, Any] = doc.get("attributes", {})
    record_id: str = str(doc.get("id", ""))

    # `title` is often a plain string; `title_display` may be wrapped.
    title = (
        (attrs.get("title") if isinstance(attrs.get("title"), str) else None)
        or _first(attrs.get("title_display"))
        or _first(attrs.get("title_citation_display"))
        or "Unknown title"
    )
    authors = _listify(
        attrs.get("author_display")
        or attrs.get("author_citation_display")
        or attrs.get("author_s")
    )
    fmt = _listify(attrs.get("format"))
    pub_date = (
        _first(attrs.get("pub_date_display"))
        or _first(attrs.get("pub_created_display"))
        or _first(attrs.get("pub_date_start_sort"))
    )
    language = _listify(
        attrs.get("language_facet")
        or attrs.get("language_name_display")
    )
    subjects = _listify(
        attrs.get("subject_display")
        or attrs.get("lc_subject_display")
        or attrs.get("subject_topic_facet")
    )

    self_link = doc.get("links", {}).get("self", "")
    url = self_link or f"https://catalog.princeton.edu/catalog/{record_id}"

    return SearchResult(
        id=record_id,
        title=title,
        authors=authors,
        format=fmt,
        pub_date=str(pub_date) if pub_date is not None else None,
        language=language,
        subjects=subjects,
        url=url,
        raw=dict(attrs),
    )


def normalize_record_response(data: dict[str, Any]) -> RecordResponse:
    """Normalize a single-record JSON:API response (``/catalog/{id}.json``)."""
    doc = data.get("data", {})
    if not doc:
        return RecordResponse(
            id="",
            title="Not found",
            url="",
            found=False,
        )
    result = normalize_doc(doc)
    return RecordResponse(**result.model_dump(), found=True)


# ── Facet normalization ───────────────────────────────────────────────────────


def normalize_facets(
    included: list[dict[str, Any]],
    desired_fields: list[str],
) -> dict[str, list[FacetValue]]:
    """Extract facet buckets from the Blacklight ``included`` block.

    Blacklight's JSON:API ``included`` section contains objects of type
    ``"facet"``; each has an ``id`` (the field name) and ``attributes``
    with a nested ``items`` list. Each item is itself a JSON:API node::

        {
          "attributes": {"value": "Book", "hits": 1234},
          "links": {...}
        }
    """
    facets: dict[str, list[FacetValue]] = {}
    for item in included:
        if item.get("type") != "facet":
            continue
        field_name = item.get("id", "")
        if desired_fields and field_name not in desired_fields:
            continue
        raw_items = item.get("attributes", {}).get("items", [])
        buckets: list[FacetValue] = []
        for fi in raw_items:
            # Items are JSON:API nodes: {attributes: {value, hits}, links: …}
            if isinstance(fi, dict) and "attributes" in fi:
                fi_attrs = fi["attributes"]
                buckets.append(
                    FacetValue(
                        value=str(fi_attrs.get("value", "")),
                        count=int(fi_attrs.get("hits", 0)),
                    )
                )
            else:
                # Flat shape fallback: {value, hits}
                buckets.append(
                    FacetValue(
                        value=str(fi.get("value", "")),
                        count=int(fi.get("hits", 0)),
                    )
                )
        facets[field_name] = buckets
    return facets


# ── Browse normalization ──────────────────────────────────────────────────────


def normalize_browse_entries(raw: list[dict[str, Any]]) -> list[BrowseEntry]:
    """Convert raw browse JSON array to :class:`BrowseEntry` list."""
    entries: list[BrowseEntry] = []
    for item in raw:
        entries.append(
            BrowseEntry(
                id=int(item.get("id", 0)),
                label=str(item.get("label", "")),
                count=int(item.get("count", 0)),
                direction=item.get("dir", "ltr"),
            )
        )
    return entries
