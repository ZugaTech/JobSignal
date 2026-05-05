import os

import pytest

from backend.core.env import EnvConfig


def test_cache_ttl_clamped(monkeypatch):
    monkeypatch.setenv("CACHE_DEFAULT_TTL_DAYS", "9")
    with pytest.raises(ValueError):
        EnvConfig.load(strict=False)


def test_strict_requires_cache_url(monkeypatch):
    monkeypatch.delenv("CACHE_URL", raising=False)
    monkeypatch.setenv("NODE_ENV", "development")
    with pytest.raises(ValueError):
        EnvConfig.load(strict=True)


def test_staging_requires_cache_url(monkeypatch):
    monkeypatch.delenv("CACHE_URL", raising=False)
    monkeypatch.setenv("NODE_ENV", "staging")
    with pytest.raises(ValueError):
        EnvConfig.load(strict=False)


def test_production_requires_cache_url(monkeypatch):
    monkeypatch.delenv("CACHE_URL", raising=False)
    monkeypatch.setenv("NODE_ENV", "production")
    with pytest.raises(ValueError):
        EnvConfig.load(strict=False)
