"""Pydantic v2 schemas for StackChat request parameters and API responses."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

# ── Shared parameter type aliases ─────────────────────────────────────────────

StrOrList = str | list[str]
SortLiteral = Literal[
    "relevance", "newest", "oldest", "title_asc", "title_desc", "author_asc"
]

# ── Common search refinement params (used by all search tools) ────────────────


class RefinementParams(BaseModel):
    """Shared optional filters accepted by every search tool."""

    format: StrOrList | None = Field(
        default=None,
        description=(
            'Limit by material type. Examples: "Book", "Journal", "Score", '
            '"Map", "Manuscript", "Audio", "Video", "Senior Thesis".'
        ),
    )
    language: StrOrList | None = Field(
        default=None,
        description='Limit by language. Examples: "English", "French", "Arabic".',
    )
    location: StrOrList | None = Field(
        default=None,
        description=(
            'Limit by library location. Examples: "Firestone Library", '
            '"Mendel Music Library", "Marquand Library", "ReCAP".'
        ),
    )
    online_only: bool = Field(
        default=False,
        description="If True, restrict to items available online.",
    )
    year_range: tuple[int | None, int | None] | None = Field(
        default=None,
        description=(
            "Inclusive publication year range as (begin, end). "
            "Either value may be None to leave that end open."
        ),
    )
    sort: SortLiteral = Field(
        default="relevance",
        description=(
            "Sort order. One of: relevance, newest, oldest, "
            "title_asc, title_desc, author_asc."
        ),
    )
    per_page: int = Field(default=10, ge=1, le=100, description="Results per page (1-100).")
    page: int = Field(default=1, ge=1, description="1-indexed page number.")

    @model_validator(mode="after")
    def _validate_year_range(self) -> RefinementParams:
        if self.year_range is not None:
            begin, end = self.year_range
            if begin is not None and end is not None and begin > end:
                raise ValueError(f"year_range begin ({begin}) must be <= end ({end})")
        return self


# ── Response models ───────────────────────────────────────────────────────────


class FacetValue(BaseModel):
    """A single facet bucket returned in a search response."""

    value: str
    count: int


class SearchResult(BaseModel):
    """A single bibliographic record in a search response."""

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    pub_date: str | None = None
    language: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    url: str
    raw: dict[str, Any] = Field(
        default_factory=dict,
        description="Original Solr field values for power users.",
    )


class SearchResponse(BaseModel):
    """Response envelope returned by all search tools."""

    total: int
    page: int
    per_page: int
    results: list[SearchResult]
    facets: dict[str, list[FacetValue]] = Field(default_factory=dict)
    next_page: int | None = None


class RecordResponse(BaseModel):
    """Full metadata for a single catalog record."""

    id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    format: list[str] = Field(default_factory=list)
    pub_date: str | None = None
    language: list[str] = Field(default_factory=list)
    subjects: list[str] = Field(default_factory=list)
    url: str
    raw: dict[str, Any] = Field(default_factory=dict)
    found: bool = True


class FacetListResponse(BaseModel):
    """Response from list_facets: enumerated values for one facet field."""

    field: str
    values: list[FacetValue]
    total_values: int


class BrowseEntry(BaseModel):
    """One entry from a browse index (names, subjects, call numbers)."""

    id: int
    label: str
    count: int
    direction: Literal["ltr", "rtl"] = "ltr"


class BrowseResponse(BaseModel):
    """Response from a browse tool."""

    query: str
    index: str
    results: list[BrowseEntry]
