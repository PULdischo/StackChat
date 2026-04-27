"""FastMCP server for StackChat — Princeton University Library catalog.

Exposes the PUL Blacklight JSON API as typed MCP tools an LLM can call
to search, browse, and fetch bibliographic records.

All search tools funnel through the private ``_search()`` helper so HTTP,
retry, caching, and response normalization logic lives in one place.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from stackchat import client as http_client
from stackchat.settings import get_port, settings
from stackchat.fields import (
    ACCESS_ONLINE,
    BROWSE_INDEXES,
    DEFAULT_RESPONSE_FACETS,
    SORT_MAP,
)
from stackchat.models import (
    BrowseResponse,
    FacetListResponse,
    FacetValue,
    RecordResponse,
    SearchResponse,
    SearchResult,
    SortLiteral,
    StrOrList,
)
from stackchat.normalize import (
    normalize_browse_entries,
    normalize_doc,
    normalize_facets,
    normalize_record_response,
)
from stackchat.validate import normalize_isbn, normalize_issn

logger = logging.getLogger(__name__)

# ── Server instance ───────────────────────────────────────────────────────────


@contextlib.asynccontextmanager
async def _lifespan(_app: Any):  # type: ignore[no-untyped-def]
    yield
    await http_client.close_client()


mcp = FastMCP(
    name="StackChat",
    instructions=(
        "Search and browse the Princeton University Library catalog. "
        "Use typed tools (search_author, search_title, etc.) rather than guessing "
        "raw Blacklight parameters. Always check the returned `facets` block to "
        "see how you can narrow a large result set. Boolean operators in `query` "
        "(AND, OR, NOT) must be UPPERCASE. The catalog contains books, journals, "
        "scores, maps, manuscripts, theses, and more — but NOT article-level content."
    ),
    lifespan=_lifespan,
)

# ── Shared parameter builder ──────────────────────────────────────────────────


def _build_params(
    *,
    search_field: str,
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> list[tuple[str, str]]:
    """Build the list of ``(param, value)`` tuples for a Blacklight search."""
    params: list[tuple[str, str]] = [
        ("search_field", search_field),
        ("q", query),
        ("per_page", str(per_page)),
        ("page", str(page)),
    ]

    sort_token = SORT_MAP.get(sort, SORT_MAP["relevance"])
    params.append(("sort", sort_token))

    # Format filter
    for fmt in (_listify(format) if format else []):
        params.append(("f[format][]", fmt))

    # Language filter
    for lang in (_listify(language) if language else []):
        params.append(("f[language_facet][]", lang))

    # Location filter
    for loc in (_listify(location) if location else []):
        params.append(("f[location][]", loc))

    # Online-only shorthand
    if online_only:
        params.append(("f[access_facet][]", ACCESS_ONLINE))

    # Year range
    if year_range is not None:
        begin, end = year_range
        if begin is not None:
            params.append(("range[pub_date_start_sort][begin]", str(begin)))
        if end is not None:
            params.append(("range[pub_date_start_sort][end]", str(end)))

    return params


def _listify(value: StrOrList | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


# ── Core search helper ────────────────────────────────────────────────────────


async def _search(
    search_field: str,
    query: str,
    *,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Private helper: build params, call the catalog, normalize the response."""
    # Validate year_range
    if year_range is not None:
        begin, end = year_range
        if begin is not None and end is not None and begin > end:
            raise ToolError(
                f"year_range begin ({begin}) must be ≤ end ({end})."
            )

    params = _build_params(
        search_field=search_field,
        query=query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )

    try:
        data = await http_client.catalog_search(params)
    except Exception as exc:
        raise ToolError(
            f"Catalog search failed: {exc}. "
            "The Princeton catalog may be temporarily unavailable."
        ) from exc

    meta_pages = data.get("meta", {}).get("pages", {})
    total = int(meta_pages.get("total_count", 0))
    current_page = int(meta_pages.get("current_page", page))
    next_page_raw = meta_pages.get("next_page")
    next_page = int(next_page_raw) if next_page_raw else None

    raw_docs = data.get("data", [])
    results: list[SearchResult] = [normalize_doc(doc) for doc in raw_docs]

    included = data.get("included", [])
    facets = normalize_facets(included, DEFAULT_RESPONSE_FACETS)

    return SearchResponse(
        total=total,
        page=current_page,
        per_page=per_page,
        results=results,
        facets=facets,
        next_page=next_page,
    )


# ── Tool definitions ──────────────────────────────────────────────────────────
# Each tool is a thin wrapper: parameter validation + fixed search_field value.
# Common refinement params are repeated in each signature so MCP hosts show
# them; they all delegate to _search().

@mcp.tool
async def search_keyword(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Search the Princeton library catalog using free-text keywords.

    Searches across title, author, subject, notes, and other fields simultaneously.
    Use this for broad discovery or when you're not sure which specific field to use.

    Boolean operators must be UPPERCASE: 'activism AND NOT Indiana'.
    Wildcards: 'algor*' matches 'algorithm', 'algorithms', etc.
    Phrase search: '"French revolution"' matches the exact phrase.

    Use `format`, `language`, `location`, `online_only`, and `year_range` to
    narrow a large result set. Check the returned `facets` block for available
    filter values.

    Example: query="plasma physics", format="Book", year_range=(1990, 2010)
    """
    return await _search(
        "all_fields",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_title(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Search for items whose title contains specific words.

    Best for: "find books with 'revolution' in the title".
    Words may appear anywhere in the title and in any order.

    For a title that *starts with* a known prefix, use `search_title_starts_with`
    instead — it uses an anchored index that handles initial articles correctly
    (e.g., skips "The" in "The Brothers Karamazov").

    Example: query="algorithms live"  →  finds "Algorithms to Live By"
    """
    return await _search(
        "title",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_title_starts_with(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find items whose title begins with an exact prefix.

    Uses an anchored left-anchor index that correctly skips MARC non-filing
    characters (initial articles like "The", "A", "Le", "Die", etc.).

    Best for: known-item lookups when you know the beginning of a title.
    Example: query="Brothers Karamazov"  →  finds "The Brothers Karamazov"
    (you don't need to include "The").

    For keyword title search (words anywhere in the title), use `search_title`.
    """
    return await _search(
        "left_anchor",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_author(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find items by an author, creator, or contributor's name.

    Name order is flexible — "Dostoevsky Fyodor" and "Fyodor Dostoevsky"
    both work. For a precise alphabetical browse through the name authority
    list, use `browse_names` instead.

    Example: query="Dostoevsky"  →  all works by Fyodor Dostoevsky
    Example: query="Princeton University Press"  →  items published by PUP
    """
    return await _search(
        "author",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_subject(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find items by Library of Congress Subject Heading (LCSH) topic words.

    Matches subject headings, subdivisions, and topical terms. You don't need
    to enter the full LCSH string — "Ottoman Empire" finds works with that
    phrase anywhere in the subject field.

    For alphabetic browsing of the full subject authority list, use
    `browse_subjects` instead.

    Example: query="climate change policy"  →  works on climate policy
    Example: query="Ottoman Empire 19th century"
    """
    return await _search(
        "subject",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_publisher(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find items published by a specific publisher.

    Example: query="Oxford University Press"
    Example: query="Gallimard"  →  items from the French publisher Gallimard
    """
    return await _search(
        "publisher",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_series(
    query: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find items that belong to a specific series.

    Example: query="Oxford Classical Monographs"
    Example: query="Penguin Classics"
    """
    return await _search(
        "series_title",
        query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_isbn(
    isbn: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find a specific edition of a book by ISBN-10 or ISBN-13.

    Accepts both formats with or without hyphens:
      "978-0-19-853453-3", "9780198534533", "0-19-853453-3", "0198534531"

    Validates the check digit before querying — returns an error immediately
    if the ISBN is malformed, before hitting the catalog.

    Note: the catalog may hold multiple editions; if you get zero results, try
    `search_title` or `search_author` to find related editions.
    """
    normalized, error = normalize_isbn(isbn)
    if error:
        raise ToolError(error)
    return await _search(
        "isbn",
        normalized,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def search_issn(
    issn: str,
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    sort: SortLiteral = "relevance",
    per_page: int = 10,
    page: int = 1,
) -> SearchResponse:
    """Find a journal or serial by ISSN.

    Accepts 8-character ISSNs with or without the hyphen:
      "0028-0836", "00280836"

    Validates the check digit before querying.

    Example: issn="0028-0836"  →  Nature (the journal)
    """
    normalized, error = normalize_issn(issn)
    if error:
        raise ToolError(error)
    return await _search(
        "issn",
        normalized,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort=sort,
        per_page=per_page,
        page=page,
    )


@mcp.tool
async def get_record(record_id: str) -> RecordResponse:
    """Fetch full metadata for a single catalog record by its MMS ID.

    The MMS ID is the long numeric Alma identifier visible in catalog URLs:
    ``https://catalog.princeton.edu/catalog/9987870933506421``
    → record_id = "9987870933506421"

    Shorter legacy bib IDs (e.g. "9987870") also resolve.

    Returns a richer field set than search results, including full subject
    headings, series, notes, and holding-location hints. Real-time shelf
    availability is NOT included — follow the `url` link for live status.
    """
    try:
        data = await http_client.catalog_record(record_id)
    except Exception as exc:
        # Surface 404 as a structured "not found" rather than a raw error
        if hasattr(exc, "response") and exc.response.status_code == 404:  # type: ignore[union-attr]
            return RecordResponse(
                id=record_id,
                title="Not found",
                url=f"https://catalog.princeton.edu/catalog/{record_id}",
                found=False,
            )
        raise ToolError(
            f"Could not fetch record '{record_id}': {exc}"
        ) from exc

    return normalize_record_response(data)


@mcp.tool
async def list_facets(
    facet_field: str,
    query: str = "*",
    format: StrOrList | None = None,
    language: StrOrList | None = None,
    location: StrOrList | None = None,
    online_only: bool = False,
    year_range: tuple[int | None, int | None] | None = None,
    per_page: int = 20,
) -> FacetListResponse:
    """Enumerate the available values for one facet field.

    Useful for discovering what format types, languages, or library locations
    are available — especially before applying a filter to a search.

    Common facet fields:
      - "format"              → Book, Journal, Score, Map, Audio, Video, …
      - "language_facet"      → English, French, German, Arabic, …
      - "location"            → Firestone Library, Mendel Music Library, …
      - "access_facet"        → Online, In the Library
      - "subject_topic_facet" → LCSH topical subject headings
      - "subject_geo_facet"   → Geographic subjects
      - "subject_era_facet"   → Era/period subjects

    You can constrain the facet to a subset by providing `query` and filter
    params; omit them to get the global distribution.

    Example: list_facets("format") → [Book: 450000, Journal: 120000, …]
    """
    params = _build_params(
        search_field="all_fields",
        query=query,
        format=format,
        language=language,
        location=location,
        online_only=online_only,
        year_range=year_range,
        sort="relevance",
        per_page=per_page,
        page=1,
    )

    try:
        data = await http_client.catalog_facet(facet_field, params)
    except Exception as exc:
        raise ToolError(
            f"Could not retrieve facet '{facet_field}': {exc}"
        ) from exc

    # Real endpoint: GET /catalog/facet/{field}.json returns:
    # {"response": {"facets": {"items": [{"value": "Book", "hits": N}, …]}}}
    values: list[FacetValue] = []
    response_block = data.get("response", {})
    facet_block = response_block.get("facets", {})
    raw_items = facet_block.get("items", [])
    for item in raw_items:
        values.append(
            FacetValue(
                value=str(item.get("value", "")),
                count=int(item.get("hits", 0)),
            )
        )

    return FacetListResponse(
        field=facet_field,
        values=values,
        total_values=len(values),
    )


@mcp.tool
async def browse_names(
    query: str,
    per_page: int = 20,
) -> BrowseResponse:
    """Browse the alphabetic name/author authority list.

    Scrolls the name authority index to the prefix you provide. Useful for:
    - Finding the canonical form of an author's name before searching.
    - Listing all authority entries near a given point in the alphabet.
    - Discovering variant forms ("Dostoevsky" vs. "Dostoyevsky").

    The results are sorted alphabetically and include a record count showing
    how many catalog items are associated with each name heading.

    Example: query="Beethoven"  →  entries starting near "Beethoven" in the
    name authority list, with record counts.

    For keyword search across author fields, use `search_author` instead.
    """
    params: list[tuple[str, str]] = [("q", query), ("rpp", str(per_page))]
    try:
        raw = await http_client.catalog_browse(BROWSE_INDEXES["names"], params)
    except Exception as exc:
        raise ToolError(f"Browse names failed: {exc}") from exc

    entries = normalize_browse_entries(raw if isinstance(raw, list) else [])
    return BrowseResponse(query=query, index="names", results=entries)


@mcp.tool
async def browse_subjects(
    query: str,
    per_page: int = 20,
) -> BrowseResponse:
    """Browse the alphabetic subject authority list.

    Scrolls the subject heading index to the prefix you provide. Useful for:
    - Discovering the exact LCSH form of a subject before filtering.
    - Walking the alphabet to find related subject headings.

    Example: query="Ottoman"  →  subject headings starting near "Ottoman",
    such as "Ottoman Empire", "Ottoman literature", etc.

    For keyword search across subject fields, use `search_subject` instead.
    """
    params: list[tuple[str, str]] = [("q", query), ("rpp", str(per_page))]
    try:
        raw = await http_client.catalog_browse(BROWSE_INDEXES["subjects"], params)
    except Exception as exc:
        raise ToolError(f"Browse subjects failed: {exc}") from exc

    entries = normalize_browse_entries(raw if isinstance(raw, list) else [])
    return BrowseResponse(query=query, index="subjects", results=entries)


@mcp.tool
async def browse_call_number(
    query: str,
    per_page: int = 20,
) -> BrowseResponse:
    """Walk the LC call-number shelf near a given call number.

    Returns the entries shelved immediately before and after the call number
    prefix you provide — effectively a virtual shelf browse.

    Useful for:
    - "What else is shelved near PN842 .S539?"
    - Exploring a classification range systematically.

    Call numbers use the Library of Congress system (LC): a letter class
    followed by a subclass and number (e.g., "PR6003.A93", "QA76.6", "ML410").

    Example: query="PN842"  →  items shelved around that call number.
    """
    params: list[tuple[str, str]] = [("q", query), ("rpp", str(per_page))]
    try:
        raw = await http_client.catalog_browse(BROWSE_INDEXES["call_numbers"], params)
    except Exception as exc:
        raise ToolError(f"Browse call numbers failed: {exc}") from exc

    entries = normalize_browse_entries(raw if isinstance(raw, list) else [])
    return BrowseResponse(query=query, index="call_numbers", results=entries)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """Run the MCP server.

    Transport is controlled by the STACKCHAT_TRANSPORT environment variable:
    - "stdio"            — default; for local Claude Desktop / Cursor use.
    - "streamable-http"  — for Cloud Run and other remote deployments.
                           Binds to 0.0.0.0:PORT (Cloud Run injects PORT).
    """
    if settings.transport == "streamable-http":
        port = get_port()
        logger.info("Starting StackChat on streamable-http transport, port %d", port)
        mcp.run(transport="streamable-http", host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
