"""Tests for the HTTP parameter builder in server.py.

These tests exercise _build_params() without making any network calls.
"""

from __future__ import annotations

import pytest

from stackchat.server import _build_params


class TestBuildParams:
    def _get(self, params: list[tuple[str, str]], key: str) -> list[str]:
        """Return all values for *key* in the params list."""
        return [v for k, v in params if k == key]

    def _get_one(self, params, key: str) -> str | None:
        vals = self._get(params, key)
        return vals[0] if vals else None

    def test_minimal_params(self):
        params = _build_params(search_field="all_fields", query="plasma physics")
        assert self._get_one(params, "search_field") == "all_fields"
        assert self._get_one(params, "q") == "plasma physics"
        assert self._get_one(params, "per_page") == "10"
        assert self._get_one(params, "page") == "1"

    def test_sort_relevance(self):
        params = _build_params(search_field="title", query="test", sort="relevance")
        sort_val = self._get_one(params, "sort")
        assert sort_val is not None
        assert "score" in sort_val

    def test_sort_newest(self):
        params = _build_params(search_field="title", query="test", sort="newest")
        sort_val = self._get_one(params, "sort")
        assert "pub_date_sort desc" in sort_val

    def test_sort_oldest(self):
        params = _build_params(search_field="title", query="test", sort="oldest")
        sort_val = self._get_one(params, "sort")
        assert "pub_date_sort asc" in sort_val

    def test_format_single_string(self):
        params = _build_params(
            search_field="all_fields", query="beethoven", format="Score"
        )
        assert ("f[format][]", "Score") in params

    def test_format_multiple(self):
        params = _build_params(
            search_field="all_fields", query="beethoven", format=["Score", "Audio"]
        )
        formats = self._get(params, "f[format][]")
        assert "Score" in formats
        assert "Audio" in formats

    def test_language_filter(self):
        params = _build_params(
            search_field="all_fields", query="test", language="German"
        )
        assert ("f[language_facet][]", "German") in params

    def test_location_filter(self):
        params = _build_params(
            search_field="all_fields",
            query="test",
            location="Mendel Music Library",
        )
        assert ("f[location][]", "Mendel Music Library") in params

    def test_online_only(self):
        params = _build_params(
            search_field="all_fields", query="test", online_only=True
        )
        assert ("f[access_facet][]", "Online") in params

    def test_online_only_false(self):
        params = _build_params(
            search_field="all_fields", query="test", online_only=False
        )
        access_vals = self._get(params, "f[access_facet][]")
        assert not access_vals

    def test_year_range_both(self):
        params = _build_params(
            search_field="all_fields", query="test", year_range=(1990, 2010)
        )
        assert ("range[pub_date_start_sort][begin]", "1990") in params
        assert ("range[pub_date_start_sort][end]", "2010") in params

    def test_year_range_begin_only(self):
        params = _build_params(
            search_field="all_fields", query="test", year_range=(2000, None)
        )
        assert ("range[pub_date_start_sort][begin]", "2000") in params
        end_vals = self._get(params, "range[pub_date_start_sort][end]")
        assert not end_vals

    def test_year_range_end_only(self):
        params = _build_params(
            search_field="all_fields", query="test", year_range=(None, 1950)
        )
        assert ("range[pub_date_start_sort][end]", "1950") in params
        begin_vals = self._get(params, "range[pub_date_start_sort][begin]")
        assert not begin_vals

    def test_per_page_and_page(self):
        params = _build_params(
            search_field="all_fields", query="test", per_page=25, page=3
        )
        assert self._get_one(params, "per_page") == "25"
        assert self._get_one(params, "page") == "3"

    def test_combined_filters(self):
        """All filters can be combined without collision."""
        params = _build_params(
            search_field="subject",
            query="beethoven symphonies",
            format="Score",
            language="German",
            location="Mendel Music Library",
            year_range=(1990, None),
            sort="newest",
            per_page=5,
            page=2,
        )
        assert self._get_one(params, "search_field") == "subject"
        assert ("f[format][]", "Score") in params
        assert ("f[language_facet][]", "German") in params
        assert ("f[location][]", "Mendel Music Library") in params
        assert ("range[pub_date_start_sort][begin]", "1990") in params
        assert self._get_one(params, "per_page") == "5"
        assert self._get_one(params, "page") == "2"
