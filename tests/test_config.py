"""Tests for config module profile support."""

from __future__ import annotations

from unittest.mock import patch

from uipath_mcp.config import get_settings
import uipath_mcp.config as _config_mod


class TestGetSettingsProfile:
    def setup_method(self):
        _config_mod._settings = None

    def teardown_method(self):
        _config_mod._settings = None

    @patch("uipath_mcp.keyring_store.load_from_keyring")
    def test_passes_profile_to_keyring(self, mock_load):
        mock_load.return_value = {}
        # Will use env vars set in conftest for actual Settings construction
        get_settings(profile="staging")
        mock_load.assert_called_once_with(profile="staging")

    @patch("uipath_mcp.keyring_store.load_from_keyring")
    def test_defaults_to_default_profile(self, mock_load):
        mock_load.return_value = {}
        get_settings()
        mock_load.assert_called_once_with(profile="default")

    @patch("uipath_mcp.keyring_store.load_from_keyring")
    def test_uipath_profile_env_var_fallback(self, mock_load):
        mock_load.return_value = {}
        import os
        with patch.dict(os.environ, {"UIPATH_PROFILE": "from-env"}):
            get_settings()
        mock_load.assert_called_once_with(profile="from-env")

    @patch("uipath_mcp.keyring_store.load_from_keyring")
    def test_explicit_profile_overrides_env_var(self, mock_load):
        mock_load.return_value = {}
        import os
        with patch.dict(os.environ, {"UIPATH_PROFILE": "from-env"}):
            get_settings(profile="explicit")
        mock_load.assert_called_once_with(profile="explicit")

    @patch("uipath_mcp.keyring_store.load_from_keyring")
    def test_read_only_from_keyring(self, mock_load):
        mock_load.return_value = {
            "auth_mode": "pat",
            "uipath_base_url": "https://example.com",
            "uipath_pat": "test_token",
            "uipath_tenant_name": "Tenant",
            "read_only_mode": "true",
        }
        settings = get_settings(profile="ro-profile")
        assert settings.read_only_mode is True

    @patch("uipath_mcp.keyring_store.load_from_keyring")
    def test_read_only_env_var_overrides_keyring(self, mock_load):
        """READ_ONLY_MODE env var should override keyring's read_only_mode."""
        mock_load.return_value = {
            "auth_mode": "pat",
            "uipath_base_url": "https://example.com",
            "uipath_pat": "test_token",
            "uipath_tenant_name": "Tenant",
            "read_only_mode": "true",
        }
        import os
        with patch.dict(os.environ, {"READ_ONLY_MODE": "false"}):
            settings = get_settings(profile="test")
        assert settings.read_only_mode is False
