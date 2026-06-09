"""Shared test fixtures.

The settings cache is lru_cache'd, so once anything reads it the values
are pinned for the process. We clear it at the start of every test that
mutates env vars to keep tests independent.
"""

from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
