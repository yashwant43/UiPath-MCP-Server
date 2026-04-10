"""Tests for keyring_store module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from uipath_mcp.keyring_store import (
    KEYRING_FIELDS,
    PROFILES_INDEX_KEY,
    PROFILES_INDEX_SERVICE,
    SERVICE_NAME,
    _get_keyring,
    add_profile_to_index,
    clear_all,
    delete_credential,
    list_profiles,
    load_from_keyring,
    read_all,
    remove_profile_from_index,
    service_name_for_profile,
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
        mock_set.assert_called_once_with("uipath-mcp/default", "uipath_pat", "my_token")


# ── clear_all() ──────────────────────────────────────────────────────────────


class TestClearAll:
    @patch("keyring.errors")
    @patch("keyring.delete_password")
    def test_clears_and_returns_count(self, mock_delete, mock_errors):
        """Counts successful deletes, ignores missing entries."""
        mock_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})

        calls = iter(range(100))

        def side_effect(svc, key):
            assert svc == "uipath-mcp/default"
            n = next(calls)
            if n >= 3:
                raise mock_errors.PasswordDeleteError("not found")

        mock_delete.side_effect = side_effect
        count = clear_all()
        assert count == 3


# ── service_name_for_profile() ──────────────────────────────────────────────


class TestServiceNameForProfile:
    def test_default_profile(self):
        assert service_name_for_profile("default") == "uipath-mcp/default"

    def test_named_profile(self):
        assert service_name_for_profile("staging") == "uipath-mcp/staging"

    def test_org_tenant_profile(self):
        assert service_name_for_profile("myorg/mytenant") == "uipath-mcp/myorg/mytenant"


# ── KEYRING_FIELDS ──────────────────────────────────────────────────────────


class TestKeyringFields:
    def test_read_only_mode_in_fields(self):
        assert "read_only_mode" in KEYRING_FIELDS


# ── load_from_keyring(profile=...) ──────────────────────────────────────────


class TestLoadFromKeyringProfile:
    def test_named_profile_loading(self):
        """Loading a named profile reads from the correct service name."""
        stored = {"auth_mode": "cloud", "uipath_client_id": "cid"}
        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = lambda svc, key: (
            stored.get(key) if svc == "uipath-mcp/staging" else None
        )

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring(profile="staging")

        assert result["auth_mode"] == "cloud"
        assert result["uipath_client_id"] == "cid"

    def test_default_profile_fallback(self):
        """Calling without profile arg uses 'default', then falls back to legacy migration."""
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            load_from_keyring()

        # First batch of calls reads from uipath-mcp/default (the profile service)
        # Then migration reads from uipath-mcp (the legacy service)
        services_called = {call[0][0] for call in mock_kr.get_password.call_args_list}
        assert "uipath-mcp/default" in services_called


# ── store_credential(profile=...) ───────────────────────────────────────────


class TestStoreCredentialProfile:
    @patch("keyring.set_password")
    def test_stores_to_named_profile(self, mock_set):
        store_credential("uipath_pat", "tok", profile="prod")
        mock_set.assert_called_once_with("uipath-mcp/prod", "uipath_pat", "tok")

    @patch("keyring.set_password")
    def test_stores_to_default_profile(self, mock_set):
        store_credential("uipath_pat", "tok")
        mock_set.assert_called_once_with("uipath-mcp/default", "uipath_pat", "tok")


# ── delete_credential(profile=...) ──────────────────────────────────────────


class TestDeleteCredentialProfile:
    @patch("keyring.errors")
    @patch("keyring.delete_password")
    def test_delete_from_named_profile(self, mock_delete, mock_errors):
        mock_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
        delete_credential("uipath_pat", profile="staging")
        mock_delete.assert_called_once_with("uipath-mcp/staging", "uipath_pat")


# ── read_all(profile=...) ───────────────────────────────────────────────────


class TestReadAllProfile:
    @patch("keyring.get_password", return_value=None)
    def test_read_from_named_profile(self, mock_get):
        read_all(profile="dev")
        for call in mock_get.call_args_list:
            assert call[0][0] == "uipath-mcp/dev"


# ── clear_all(profile=...) ──────────────────────────────────────────────────


class TestClearAllProfile:
    @patch("keyring.errors")
    @patch("keyring.delete_password")
    def test_clear_named_profile(self, mock_delete, mock_errors):
        mock_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
        clear_all(profile="staging")
        for call in mock_delete.call_args_list:
            assert call[0][0] == "uipath-mcp/staging"


# ── Profile Index ──────────────────────────────────────────────────────────


class TestProfileIndex:
    @patch("keyring.get_password", return_value=None)
    def test_list_profiles_empty(self, mock_get):
        assert list_profiles() == []

    @patch("keyring.get_password", return_value="default,prod")
    def test_list_profiles_returns_names(self, mock_get):
        assert list_profiles() == ["default", "prod"]
        mock_get.assert_called_once_with(PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY)

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value=None)
    def test_add_first_profile(self, mock_get, mock_set):
        add_profile_to_index("prod")
        mock_set.assert_called_once_with(PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, "prod")

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default")
    def test_add_second_profile(self, mock_get, mock_set):
        add_profile_to_index("prod")
        mock_set.assert_called_once_with(PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, "default,prod")

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default,prod")
    def test_add_duplicate_is_noop(self, mock_get, mock_set):
        add_profile_to_index("prod")
        mock_set.assert_not_called()

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default,prod,staging")
    def test_remove_profile(self, mock_get, mock_set):
        remove_profile_from_index("prod")
        mock_set.assert_called_once_with(PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, "default,staging")

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default,prod,staging")
    def test_remove_nonexistent_is_noop(self, mock_get, mock_set):
        remove_profile_from_index("missing")
        mock_set.assert_not_called()


# ── _migrate_legacy_credentials / load_from_keyring migration ──────────────


class TestMigrateLegacyCredentials:
    def test_migrates_old_credentials_to_default_profile(self):
        """When uipath-mcp has creds but uipath-mcp/default doesn't, migrate."""
        legacy_data = {
            ("uipath-mcp", "auth_mode"): "pat",
            ("uipath-mcp", "uipath_pat"): "old_token",
            ("uipath-mcp", "uipath_base_url"): "https://example.com",
            ("uipath-mcp", "uipath_tenant_name"): "Tenant1",
        }

        def mock_get(svc, key):
            return legacy_data.get((svc, key))

        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = mock_get
        mock_kr.set_password = MagicMock()
        mock_kr.delete_password = MagicMock()

        with (
            patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr),
            patch("uipath_mcp.keyring_store.add_profile_to_index") as mock_add_idx,
        ):
            result = load_from_keyring(profile="default")

        assert result["auth_mode"] == "pat"
        assert result["uipath_pat"] == "old_token"

        set_calls = {(c.args[0], c.args[1]): c.args[2] for c in mock_kr.set_password.call_args_list}
        assert set_calls[("uipath-mcp/default", "auth_mode")] == "pat"
        assert set_calls[("uipath-mcp/default", "uipath_pat")] == "old_token"

        delete_calls = [(c.args[0], c.args[1]) for c in mock_kr.delete_password.call_args_list]
        assert ("uipath-mcp", "auth_mode") in delete_calls

        mock_add_idx.assert_called_once_with("default")

    def test_no_migration_when_default_has_creds(self):
        """If uipath-mcp/default already has credentials, skip migration."""
        data = {
            ("uipath-mcp/default", "auth_mode"): "cloud",
            ("uipath-mcp", "auth_mode"): "pat",
        }

        def mock_get(svc, key):
            return data.get((svc, key))

        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = mock_get

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring(profile="default")

        assert result["auth_mode"] == "cloud"
        mock_kr.set_password.assert_not_called()

    def test_no_migration_for_non_default_profile(self):
        """Migration only runs for the 'default' profile."""
        mock_kr = MagicMock()
        mock_kr.get_password.return_value = None

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring(profile="prod")

        assert result == {}
        mock_kr.set_password.assert_not_called()
