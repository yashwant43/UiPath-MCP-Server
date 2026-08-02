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
        mock_start.assert_called_once_with(profile=None)


class TestServerStartProfile:
    @patch("uipath_mcp.cli._start_server")
    def test_profile_flag_passed_to_start_server(self, mock_start):
        runner = CliRunner()
        runner.invoke(main, ["--profile", "prod"])
        mock_start.assert_called_once_with(profile="prod")


# ── auth help ────────────────────────────────────────────────────────────────


class TestAuthHelp:
    def test_shows_subcommands(self):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "--help"])
        assert "setup" in result.output
        assert "test" in result.output
        assert "clear" in result.output
        assert "list" in result.output


# ── auth setup ───────────────────────────────────────────────────────────────


class TestAuthSetup:
    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_pat_setup_stores_credentials(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # Prompts: base_url, pat, tenant, folder_id(skip), folder_path(skip), read-only(n)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "default"],
            input="https://example.com\nmy_pat_token\nTestTenant\n\n\nn\n",
        )
        assert result.exit_code == 0, result.output

        stored_fields = [call.args[0] for call in mock_store.call_args_list]
        assert "auth_mode" in stored_fields
        assert "uipath_base_url" in stored_fields
        assert "uipath_pat" in stored_fields
        assert "uipath_tenant_name" in stored_fields
        mock_add_profile.assert_called_once_with("default")

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_cloud_setup_stores_credentials(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # Prompts: client_id, client_secret, org, tenant, folder_id(skip), folder_path(skip), read-only(n)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "cloud", "--profile", "default"],
            input="my_client_id\nmy_secret\nmy_org\nDefaultTenant\n\n\nn\n",
        )
        assert result.exit_code == 0, result.output

        stored_fields = [call.args[0] for call in mock_store.call_args_list]
        assert "auth_mode" in stored_fields
        assert "uipath_client_id" in stored_fields
        assert "uipath_client_secret" in stored_fields
        assert "uipath_org_name" in stored_fields
        mock_add_profile.assert_called_once_with("default")


# ── auth setup with profile ─────────────────────────────────────────────────


class TestAuthSetupProfile:
    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_explicit_profile(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # --profile prod given, so no profile name prompt
        # Prompts: base_url, pat, tenant, folder_id(skip), folder_path(skip), read-only(n)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "prod"],
            input="https://example.com\nmy_pat\nProdTenant\n\n\nn\n",
        )
        assert result.exit_code == 0, result.output
        # All store calls should use profile="prod"
        for call in mock_store.call_args_list:
            assert call.kwargs.get("profile") == "prod"
        mock_add_profile.assert_called_once_with("prod")

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_auto_derive_cloud_profile(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # No --profile, so auto-derive from org/tenant and prompt
        # Prompts: client_id, client_secret, org, tenant, folder_id(skip), folder_path(skip),
        #          read-only(n), profile name (accept derived = my_org/MyTenant)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "cloud"],
            input="cid\nsecret\nmy_org\nMyTenant\n\n\nn\n\n",
        )
        assert result.exit_code == 0, result.output
        # Should derive profile name as "my_org/MyTenant"
        mock_add_profile.assert_called_once_with("my_org/MyTenant")

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_auto_derive_pat_profile(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # No --profile for PAT mode: derive from tenant name
        # Prompts: base_url, pat, tenant, folder_id(skip), folder_path(skip),
        #          read-only(n), profile name (accept derived = DevTenant)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat"],
            input="https://example.com\ntoken\nDevTenant\n\n\nn\n\n",
        )
        assert result.exit_code == 0, result.output
        mock_add_profile.assert_called_once_with("DevTenant")


# ── auth setup read-only ─────────────────────────────────────────────────────


class TestAuthSetupReadOnly:
    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_read_only_yes_stores_field(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # Prompts: base_url, pat, tenant, folder_id(skip), folder_path(skip), read-only(y)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "ro"],
            input="https://example.com\nmy_pat\nTenant\n\n\ny\n",
        )
        assert result.exit_code == 0, result.output
        stored = {call.args[0]: call.args[1] for call in mock_store.call_args_list}
        assert stored.get("read_only_mode") == "true"

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_read_only_no_does_not_store(self, mock_store, mock_add_profile):
        runner = CliRunner()
        # Prompts: base_url, pat, tenant, folder_id(skip), folder_path(skip), read-only(n)
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "rw"],
            input="https://example.com\nmy_pat\nTenant\n\n\nn\n",
        )
        assert result.exit_code == 0, result.output
        stored_fields = [call.args[0] for call in mock_store.call_args_list]
        assert "read_only_mode" not in stored_fields


# ── auth test ────────────────────────────────────────────────────────────────


class TestAuthTest:
    @patch("uipath_mcp.keyring_store.read_all")
    def test_no_credentials_exits_1(self, mock_read):
        mock_read.return_value = {}
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "test"])
        assert result.exit_code == 1
        assert "No credentials" in result.output
        mock_read.assert_called_once_with(profile="default")

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
        assert "****" in result.output
        assert "https://example.com" in result.output
        mock_read.assert_called_once_with(profile="default")


class TestAuthTestProfile:
    @patch("uipath_mcp.config.Settings")
    @patch("uipath_mcp.keyring_store.read_all")
    def test_profile_flag_passed(self, mock_read, mock_settings_cls):
        mock_read.return_value = {
            "auth_mode": "pat",
            "uipath_base_url": "https://staging.example.com",
            "uipath_pat": "secret",
            "uipath_tenant_name": "Staging",
        }
        mock_settings = MagicMock()
        mock_settings.auth_mode.value = "pat"
        mock_settings.orchestrator_base_url = "https://staging.example.com"
        mock_settings_cls.return_value = mock_settings

        runner = CliRunner()
        result = runner.invoke(main, ["auth", "test", "--profile", "staging"])
        assert result.exit_code == 0
        mock_read.assert_called_once_with(profile="staging")
        assert "staging" in result.output


# ── auth clear ───────────────────────────────────────────────────────────────


class TestAuthClear:
    @patch("uipath_mcp.cli._remove_profile_from_index")
    @patch("uipath_mcp.keyring_store.clear_all", return_value=5)
    def test_clears_with_confirmation(self, mock_clear, mock_remove_profile):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear", "--yes"])
        assert result.exit_code == 0
        mock_clear.assert_called_once_with(profile="default")
        mock_remove_profile.assert_called_once_with("default")
        assert "5" in result.output

    @patch("uipath_mcp.cli._remove_profile_from_index")
    @patch("uipath_mcp.keyring_store.clear_all")
    def test_aborts_without_confirmation(self, mock_clear, mock_remove_profile):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear"])
        mock_clear.assert_not_called()
        mock_remove_profile.assert_not_called()


class TestAuthClearProfile:
    @patch("uipath_mcp.cli._remove_profile_from_index")
    @patch("uipath_mcp.keyring_store.clear_all", return_value=3)
    def test_clears_with_profile(self, mock_clear, mock_remove_profile):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear", "--profile", "staging", "--yes"])
        assert result.exit_code == 0
        mock_clear.assert_called_once_with(profile="staging")
        mock_remove_profile.assert_called_once_with("staging")


# ── auth list ────────────────────────────────────────────────────────────────


class TestAuthList:
    @patch("uipath_mcp.keyring_store.read_all")
    @patch("uipath_mcp.keyring_store.list_profiles")
    def test_list_shows_profiles(self, mock_list, mock_read):
        mock_list.return_value = ["default", "prod"]
        mock_read.side_effect = [
            {
                "auth_mode": "pat",
                "uipath_tenant_name": "Dev",
            },
            {
                "auth_mode": "cloud",
                "uipath_org_name": "acme",
                "uipath_tenant_name": "Prod",
                "read_only_mode": "true",
            },
        ]

        runner = CliRunner()
        result = runner.invoke(main, ["auth", "list"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "prod" in result.output
        assert "pat" in result.output
        assert "cloud" in result.output

    @patch("uipath_mcp.keyring_store.list_profiles")
    def test_empty_list(self, mock_list):
        mock_list.return_value = []
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "list"])
        assert result.exit_code == 0
        assert "No profiles found" in result.output
