"""Pytest configuration and shared fixtures."""

from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


@pytest.fixture
def search_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "search_response.json").read_text())


@pytest.fixture
def record_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "record_response.json").read_text())


@pytest.fixture
def empty_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "empty_response.json").read_text())


@pytest.fixture
def facet_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "facet_response.json").read_text())
