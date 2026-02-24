"""Tests for the CLI entry point."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from uipath_mcp.cli import main


# ── Default (server start) ───────────────────────────────────────────────────


class TestServerStart:
    @patch("uipath_mcp.cli._start_server")
    def test_no_args_starts_server(self, mock_start):
        runner = CliRunner()
        runner.invoke(main)
        mock_start.assert_called_once()


# ── auth help ────────────────────────────────────────────────────────────────


class TestAuthHelp:
    def test_shows_subcommands(self):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "--help"])
        assert "setup" in result.output
        assert "test" in result.output
        assert "clear" in result.output


# ── auth setup ───────────────────────────────────────────────────────────────


class TestAuthSetup:
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_pat_setup_stores_credentials(self, mock_store):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat"],
            input="https://example.com\nmy_pat_token\nTestTenant\n\n\n",
        )
        assert result.exit_code == 0, result.output

        # Should have stored: auth_mode + base_url + pat + tenant_name = 4 calls minimum
        stored_fields = [call.args[0] for call in mock_store.call_args_list]
        assert "auth_mode" in stored_fields
        assert "uipath_base_url" in stored_fields
        assert "uipath_pat" in stored_fields
        assert "uipath_tenant_name" in stored_fields

    @patch("uipath_mcp.keyring_store.store_credential")
    def test_cloud_setup_stores_credentials(self, mock_store):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "cloud"],
            input="my_client_id\nmy_secret\nmy_org\nDefaultTenant\n\n\n",
        )
        assert result.exit_code == 0, result.output

        stored_fields = [call.args[0] for call in mock_store.call_args_list]
        assert "auth_mode" in stored_fields
        assert "uipath_client_id" in stored_fields
        assert "uipath_client_secret" in stored_fields
        assert "uipath_org_name" in stored_fields


# ── auth test ────────────────────────────────────────────────────────────────


class TestAuthTest:
    @patch("uipath_mcp.keyring_store.read_all")
    def test_no_credentials_exits_1(self, mock_read):
        mock_read.return_value = {}
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "test"])
        assert result.exit_code == 1
        assert "No credentials" in result.output

    @patch("uipath_mcp.config.Settings")
    @patch("uipath_mcp.keyring_store.read_all")
    def test_valid_credentials_show_table(self, mock_read, mock_settings_cls):
        mock_read.return_value = {
            "auth_mode": "pat",
            "uipath_base_url": "https://example.com",
            "uipath_pat": "secret",
            "uipath_tenant_name": "TestTenant",
        }
        mock_settings = MagicMock()
        mock_settings.auth_mode.value = "pat"
        mock_settings.orchestrator_base_url = "https://example.com"
        mock_settings_cls.return_value = mock_settings

        runner = CliRunner()
        result = runner.invoke(main, ["auth", "test"])
        assert result.exit_code == 0
        # Secret should be masked
        assert "****" in result.output
        # Non-secret should be visible
        assert "https://example.com" in result.output


# ── auth clear ───────────────────────────────────────────────────────────────


class TestAuthClear:
    @patch("uipath_mcp.keyring_store.clear_all", return_value=5)
    def test_clears_with_confirmation(self, mock_clear):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear", "--yes"])
        assert result.exit_code == 0
        mock_clear.assert_called_once()
        assert "5" in result.output

    @patch("uipath_mcp.keyring_store.clear_all")
    def test_aborts_without_confirmation(self, mock_clear):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear"])
        mock_clear.assert_not_called()
