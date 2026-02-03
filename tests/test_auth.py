"""Tests for exogram.execution.auth module."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from exogram.execution.auth import (
    CDP_INCOMPATIBLE_COOKIE_FIELDS,
    _clean_cookie_for_cdp,
    get_auth_file_path,
    get_cdp_compatible_auth_file,
    list_available_auth_domains,
)


class TestCleanCookieForCdp:
    """Tests for _clean_cookie_for_cdp function."""

    def test_removes_incompatible_fields(self):
        cookie = {
            "name": "session",
            "value": "abc123",
            "domain": "example.com",
            "partitionKey": "some_key",
            "_crHasCrossSiteAncestor": True,
        }
        cleaned = _clean_cookie_for_cdp(cookie)
        
        assert "name" in cleaned
        assert "value" in cleaned
        assert "domain" in cleaned
        assert "partitionKey" not in cleaned
        assert "_crHasCrossSiteAncestor" not in cleaned

    def test_preserves_compatible_fields(self):
        cookie = {
            "name": "session",
            "value": "abc123",
            "domain": "example.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
        }
        cleaned = _clean_cookie_for_cdp(cookie)
        
        assert cleaned == cookie


class TestGetAuthFilePath:
    """Tests for get_auth_file_path function."""

    def test_returns_none_for_empty_url(self):
        assert get_auth_file_path("") is None

    def test_returns_none_for_nonexistent_dir(self):
        result = get_auth_file_path(
            "https://example.com",
            auth_dir=Path("/nonexistent/path"),
        )
        assert result is None

    def test_finds_exact_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_dir = Path(tmpdir)
            auth_file = auth_dir / "example.com.json"
            auth_file.write_text("{}")
            
            result = get_auth_file_path(
                "https://example.com/path",
                auth_dir=auth_dir,
            )
            assert result == auth_file

    def test_finds_base_domain_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_dir = Path(tmpdir)
            auth_file = auth_dir / "example.com.json"
            auth_file.write_text("{}")
            
            result = get_auth_file_path(
                "https://sub.example.com/path",
                auth_dir=auth_dir,
            )
            assert result == auth_file

    def test_finds_sibling_domain_match(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_dir = Path(tmpdir)
            auth_file = auth_dir / "sso.example.com.json"
            auth_file.write_text("{}")
            
            result = get_auth_file_path(
                "https://app.example.com/path",
                auth_dir=auth_dir,
            )
            assert result == auth_file


class TestListAvailableAuthDomains:
    """Tests for list_available_auth_domains function."""

    def test_returns_empty_for_nonexistent_dir(self):
        result = list_available_auth_domains(
            auth_dir=Path("/nonexistent/path")
        )
        assert result == []

    def test_lists_domains(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_dir = Path(tmpdir)
            (auth_dir / "example.com.json").write_text("{}")
            (auth_dir / "test.com.json").write_text("{}")
            
            result = list_available_auth_domains(auth_dir=auth_dir)
            assert len(result) == 2
            assert "example.com" in result
            assert "test.com" in result


class TestGetCdpCompatibleAuthFile:
    """Tests for get_cdp_compatible_auth_file function."""

    def test_returns_none_for_no_auth_file(self):
        result = get_cdp_compatible_auth_file(
            "https://example.com",
            auth_dir=Path("/nonexistent/path"),
        )
        assert result is None

    def test_creates_cached_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_dir = Path(tmpdir)
            auth_file = auth_dir / "example.com.json"
            state = {
                "cookies": [
                    {
                        "name": "session",
                        "value": "abc",
                        "partitionKey": "key",
                    }
                ],
                "origins": [],
            }
            auth_file.write_text(json.dumps(state))
            
            result = get_cdp_compatible_auth_file(
                "https://example.com",
                auth_dir=auth_dir,
            )
            
            assert result is not None
            assert Path(result).exists()
            
            # Verify the cached file has cleaned cookies
            cached_state = json.loads(Path(result).read_text())
            assert "partitionKey" not in cached_state["cookies"][0]

    def test_uses_cache_when_valid(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            auth_dir = Path(tmpdir)
            auth_file = auth_dir / "example.com.json"
            state = {"cookies": [], "origins": []}
            auth_file.write_text(json.dumps(state))
            
            # First call creates cache
            result1 = get_cdp_compatible_auth_file(
                "https://example.com",
                auth_dir=auth_dir,
            )
            
            # Second call should return the same cache file
            result2 = get_cdp_compatible_auth_file(
                "https://example.com",
                auth_dir=auth_dir,
            )
            
            assert result1 == result2
