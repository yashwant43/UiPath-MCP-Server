"""Tests for keyring_store module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from uipath_mcp.keyring_store import (
    SERVICE_NAME,
    _get_keyring,
    clear_all,
    load_from_keyring,
    store_credential,
)


# ── _get_keyring() ────────────────────────────────────────────────────────────


class TestGetKeyring:
    def test_returns_none_when_get_keyring_raises(self):
        """If keyring.get_keyring() raises, returns None gracefully."""
        mock_kr = MagicMock()
        mock_kr.get_keyring.side_effect = RuntimeError("no backend")
        with patch.dict("sys.modules", {"keyring": mock_kr}):
            result = _get_keyring()
        assert result is None

    def test_returns_none_for_fail_backend(self):
        """A FailKeyring backend is detected and skipped."""
        FailKeyring = type("FailKeyring", (), {})
        fail_backend = FailKeyring()

        with patch("keyring.get_keyring", return_value=fail_backend):
            result = _get_keyring()
        assert result is None

    def test_returns_module_for_good_backend(self):
        """A usable backend (e.g. WinVaultKeyring) returns the keyring module."""
        WinVaultKeyring = type("WinVaultKeyring", (), {})
        good_backend = WinVaultKeyring()

        with patch("keyring.get_keyring", return_value=good_backend):
            result = _get_keyring()
        assert result is not None


# ── load_from_keyring() ──────────────────────────────────────────────────────


class TestLoadFromKeyring:
    def test_returns_empty_when_keyring_unavailable(self):
        """When no usable keyring backend exists, returns empty dict."""
        with patch("uipath_mcp.keyring_store._get_keyring", return_value=None):
            assert load_from_keyring() == {}

    def test_returns_stored_values(self):
        """Reads values from keyring for fields that have entries."""
        stored = {
            "auth_mode": "pat",
            "uipath_pat": "secret_token",
            "uipath_base_url": "https://example.com",
            "uipath_tenant_name": "TestTenant",
        }
        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = lambda svc, key: stored.get(key)

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring()

        assert result["auth_mode"] == "pat"
        assert result["uipath_pat"] == "secret_token"
        assert result["uipath_base_url"] == "https://example.com"
        assert result["uipath_tenant_name"] == "TestTenant"
        assert "uipath_client_id" not in result

    def test_returns_empty_on_exception(self):
        """If keyring.get_password raises, returns empty dict gracefully."""
        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = Exception("keyring locked")

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            assert load_from_keyring() == {}


# ── store_credential() ───────────────────────────────────────────────────────


class TestStoreCredential:
    @patch("keyring.set_password")
    def test_stores_value(self, mock_set):
        store_credential("uipath_pat", "my_token")
        mock_set.assert_called_once_with(SERVICE_NAME, "uipath_pat", "my_token")


# ── clear_all() ──────────────────────────────────────────────────────────────


class TestClearAll:
    @patch("keyring.errors")
    @patch("keyring.delete_password")
    def test_clears_and_returns_count(self, mock_delete, mock_errors):
        """Counts successful deletes, ignores missing entries."""
        mock_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})

        calls = iter(range(100))

        def side_effect(svc, key):
            n = next(calls)
            if n >= 3:
                raise mock_errors.PasswordDeleteError("not found")

        mock_delete.side_effect = side_effect
        count = clear_all()
        assert count == 3
