# Multi-Tenant Profile Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Support multiple UiPath tenant credential sets in the OS keyring, selectable per server session via `--profile`.

**Architecture:** Namespace keyring entries by profile name (`uipath-mcp/<profile>`). A profile index stored at `uipath-mcp/__profiles__` tracks known profiles. CLI commands gain `--profile` flags, and the server startup resolves profile from CLI flag → env var → `"default"`. Existing single-tenant credentials are auto-migrated to the `"default"` profile.

**Tech Stack:** Python 3.12, Click, keyring, pydantic-settings, Rich, pytest

---

## File Structure

| File | Role |
|---|---|
| `src/uipath_mcp/keyring_store.py` | Profile-namespaced keyring CRUD, profile index, migration |
| `src/uipath_mcp/cli.py` | `--profile` on all commands, `auth list`, read-only prompt in setup |
| `src/uipath_mcp/config.py` | `get_settings(profile)`, profile-aware keyring loading |
| `tests/test_keyring_store.py` | Tests for profile storage, index, migration |
| `tests/test_cli.py` | Tests for CLI profile flags, `auth list`, setup with read-only |
| `tests/conftest.py` | Update `no_keyring` fixture for new signature |

---

### Task 1: Profile-Namespaced Keyring Storage

**Files:**
- Modify: `src/uipath_mcp/keyring_store.py`
- Modify: `tests/test_keyring_store.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Update conftest `no_keyring` fixture for new `load_from_keyring` signature**

The new `load_from_keyring` will accept a `profile` parameter. Update the mock to accept any args/kwargs.

In `tests/conftest.py`, replace:

```python
@pytest.fixture(autouse=True)
def no_keyring():
    """Prevent keyring from being used during tests."""
    with patch("uipath_mcp.keyring_store.load_from_keyring", return_value={}):
        yield
```

With:

```python
@pytest.fixture(autouse=True)
def no_keyring():
    """Prevent keyring from being used during tests."""
    with patch("uipath_mcp.keyring_store.load_from_keyring", return_value={}):
        yield
    # Note: load_from_keyring now accepts profile= kwarg, but MagicMock
    # handles extra args/kwargs by default, so no signature change needed.
```

Run: `uv run pytest tests/conftest.py -v`
Expected: collection passes (conftest is not a test file, but ensures no import errors).

- [ ] **Step 2: Write failing tests for `service_name_for_profile` and `KEYRING_FIELDS` update**

Add to `tests/test_keyring_store.py`:

```python
from uipath_mcp.keyring_store import (
    KEYRING_FIELDS,
    service_name_for_profile,
)


class TestServiceNameForProfile:
    def test_default_profile(self):
        assert service_name_for_profile("default") == "uipath-mcp/default"

    def test_named_profile(self):
        assert service_name_for_profile("prod") == "uipath-mcp/prod"

    def test_org_tenant_profile(self):
        assert service_name_for_profile("myorg/mytenant") == "uipath-mcp/myorg/mytenant"


class TestKeyringFields:
    def test_read_only_mode_in_fields(self):
        assert "read_only_mode" in KEYRING_FIELDS
```

Run: `uv run pytest tests/test_keyring_store.py::TestServiceNameForProfile -v`
Expected: FAIL — `service_name_for_profile` does not exist yet.

- [ ] **Step 3: Implement `service_name_for_profile` and add `read_only_mode` to KEYRING_FIELDS**

In `src/uipath_mcp/keyring_store.py`:

Replace `SERVICE_NAME = "uipath-mcp"` and add the helper. Keep `SERVICE_NAME` as a constant for the base prefix and migration:

```python
SERVICE_NAME = "uipath-mcp"

KEYRING_FIELDS: tuple[str, ...] = (
    "auth_mode",
    "uipath_client_id",
    "uipath_client_secret",
    "uipath_org_name",
    "uipath_tenant_name",
    "uipath_base_url",
    "uipath_username",
    "uipath_password",
    "uipath_pat",
    "uipath_folder_id",
    "uipath_folder_path",
    "read_only_mode",
)

PROFILES_INDEX_SERVICE = f"{SERVICE_NAME}/__profiles__"
PROFILES_INDEX_KEY = "profiles"


def service_name_for_profile(profile: str) -> str:
    """Return the keyring service name for a given profile."""
    return f"{SERVICE_NAME}/{profile}"
```

Run: `uv run pytest tests/test_keyring_store.py::TestServiceNameForProfile tests/test_keyring_store.py::TestKeyringFields -v`
Expected: PASS

- [ ] **Step 4: Write failing tests for profile-aware `load_from_keyring`**

Add to `tests/test_keyring_store.py`:

```python
class TestLoadFromKeyringProfile:
    def test_loads_from_named_profile(self):
        """load_from_keyring reads from uipath-mcp/<profile> service."""
        stored = {
            "auth_mode": "pat",
            "uipath_pat": "secret_token",
            "uipath_base_url": "https://example.com",
            "uipath_tenant_name": "TestTenant",
        }
        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = (
            lambda svc, key: stored.get(key) if svc == "uipath-mcp/prod" else None
        )

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring(profile="prod")

        assert result["auth_mode"] == "pat"
        assert result["uipath_pat"] == "secret_token"

    def test_defaults_to_default_profile(self):
        """When no profile given, uses 'default'."""
        stored = {"auth_mode": "cloud"}
        mock_kr = MagicMock()
        mock_kr.get_password.side_effect = (
            lambda svc, key: stored.get(key) if svc == "uipath-mcp/default" else None
        )

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring()

        assert result["auth_mode"] == "cloud"
```

Run: `uv run pytest tests/test_keyring_store.py::TestLoadFromKeyringProfile -v`
Expected: FAIL — `load_from_keyring` doesn't accept `profile` yet.

- [ ] **Step 5: Implement profile-aware `load_from_keyring`**

In `src/uipath_mcp/keyring_store.py`, replace the existing `load_from_keyring`:

```python
def load_from_keyring(profile: str = "default") -> dict[str, Any]:
    """Load all stored credentials from the OS keyring for a given profile.

    Returns a dict of ``{field_name: value}`` for fields that exist.
    Returns an empty dict if the keyring is unavailable or any read fails.
    """
    kr = _get_keyring()
    if kr is None:
        return {}

    svc = service_name_for_profile(profile)
    values: dict[str, Any] = {}
    try:
        for field in KEYRING_FIELDS:
            value = kr.get_password(svc, field)
            if value is not None:
                values[field] = value
    except Exception as exc:
        logger.warning(f"Failed to read from keyring: {exc}. Falling back to env vars.")
        return {}

    if values:
        logger.debug(f"Loaded {len(values)} credential(s) from keyring profile '{profile}'")
    return values
```

Run: `uv run pytest tests/test_keyring_store.py::TestLoadFromKeyringProfile tests/test_keyring_store.py::TestLoadFromKeyring -v`
Expected: ALL PASS (old tests still pass since default profile is used).

- [ ] **Step 6: Write failing tests for profile-aware `store_credential`, `delete_credential`, `read_all`, `clear_all`**

Add to `tests/test_keyring_store.py`:

```python
from uipath_mcp.keyring_store import (
    delete_credential,
    read_all,
)


class TestStoreCredentialProfile:
    @patch("keyring.set_password")
    def test_stores_to_named_profile(self, mock_set):
        store_credential("uipath_pat", "my_token", profile="prod")
        mock_set.assert_called_once_with("uipath-mcp/prod", "uipath_pat", "my_token")

    @patch("keyring.set_password")
    def test_stores_to_default_profile(self, mock_set):
        store_credential("uipath_pat", "my_token")
        mock_set.assert_called_once_with("uipath-mcp/default", "uipath_pat", "my_token")


class TestDeleteCredentialProfile:
    @patch("keyring.errors")
    @patch("keyring.delete_password")
    def test_deletes_from_named_profile(self, mock_delete, mock_errors):
        mock_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
        delete_credential("uipath_pat", profile="prod")
        mock_delete.assert_called_once_with("uipath-mcp/prod", "uipath_pat")


class TestReadAllProfile:
    @patch("keyring.get_password")
    def test_reads_from_named_profile(self, mock_get):
        mock_get.side_effect = (
            lambda svc, key: "pat" if svc == "uipath-mcp/staging" and key == "auth_mode" else None
        )
        result = read_all(profile="staging")
        assert result == {"auth_mode": "pat"}


class TestClearAllProfile:
    @patch("keyring.errors")
    @patch("keyring.delete_password")
    def test_clears_named_profile(self, mock_delete, mock_errors):
        mock_errors.PasswordDeleteError = type("PasswordDeleteError", (Exception,), {})
        call_count = [0]

        def side_effect(svc, key):
            if svc != "uipath-mcp/staging":
                raise AssertionError(f"Wrong service: {svc}")
            call_count[0] += 1

        mock_delete.side_effect = side_effect
        clear_all(profile="staging")
        assert call_count[0] == len(KEYRING_FIELDS)
```

Run: `uv run pytest tests/test_keyring_store.py::TestStoreCredentialProfile -v`
Expected: FAIL — `store_credential` doesn't accept `profile` yet.

- [ ] **Step 7: Implement profile-aware `store_credential`, `delete_credential`, `read_all`, `clear_all`**

In `src/uipath_mcp/keyring_store.py`, update all four functions:

```python
def store_credential(field: str, value: str, profile: str = "default") -> None:
    """Store a single credential in the OS keyring for a given profile."""
    import keyring

    keyring.set_password(service_name_for_profile(profile), field, value)


def delete_credential(field: str, profile: str = "default") -> None:
    """Delete a single credential from the OS keyring (no-op if absent)."""
    import keyring
    import keyring.errors

    try:
        keyring.delete_password(service_name_for_profile(profile), field)
    except keyring.errors.PasswordDeleteError:
        pass


def clear_all(profile: str = "default") -> int:
    """Delete all UiPath credentials from the OS keyring for a given profile. Returns count deleted."""
    import keyring
    import keyring.errors

    svc = service_name_for_profile(profile)
    count = 0
    for field in KEYRING_FIELDS:
        try:
            keyring.delete_password(svc, field)
            count += 1
        except keyring.errors.PasswordDeleteError:
            pass
    return count


def read_all(profile: str = "default") -> dict[str, str]:
    """Read all stored credentials for a profile (for display in ``auth test``)."""
    import keyring

    svc = service_name_for_profile(profile)
    result: dict[str, str] = {}
    for field in KEYRING_FIELDS:
        value = keyring.get_password(svc, field)
        if value is not None:
            result[field] = value
    return result
```

Run: `uv run pytest tests/test_keyring_store.py -v`
Expected: ALL PASS

- [ ] **Step 8: Update old `TestStoreCredential` and `TestClearAll` for new signatures**

The old `TestStoreCredential.test_stores_value` asserts `mock_set.assert_called_once_with(SERVICE_NAME, ...)` which is now wrong (service name is `uipath-mcp/default`). Update:

In `tests/test_keyring_store.py`, update `TestStoreCredential`:

```python
class TestStoreCredential:
    @patch("keyring.set_password")
    def test_stores_value(self, mock_set):
        store_credential("uipath_pat", "my_token")
        mock_set.assert_called_once_with("uipath-mcp/default", "uipath_pat", "my_token")
```

Update `TestClearAll` to expect the new service name pattern:

```python
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
```

Run: `uv run pytest tests/test_keyring_store.py -v`
Expected: ALL PASS

- [ ] **Step 9: Commit**

```bash
git add src/uipath_mcp/keyring_store.py tests/test_keyring_store.py tests/conftest.py
git commit -m "feat: add profile-namespaced keyring storage"
```

---

### Task 2: Profile Index (List/Add/Remove Profiles)

**Files:**
- Modify: `src/uipath_mcp/keyring_store.py`
- Modify: `tests/test_keyring_store.py`

- [ ] **Step 1: Write failing tests for profile index functions**

Add to `tests/test_keyring_store.py`:

```python
from uipath_mcp.keyring_store import (
    list_profiles,
    add_profile_to_index,
    remove_profile_from_index,
    PROFILES_INDEX_SERVICE,
    PROFILES_INDEX_KEY,
)


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
        mock_set.assert_called_once_with(
            PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, "prod"
        )

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default")
    def test_add_second_profile(self, mock_get, mock_set):
        add_profile_to_index("prod")
        mock_set.assert_called_once_with(
            PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, "default,prod"
        )

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default,prod")
    def test_add_duplicate_is_noop(self, mock_get, mock_set):
        add_profile_to_index("prod")
        mock_set.assert_not_called()

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default,prod,staging")
    def test_remove_profile(self, mock_get, mock_set):
        remove_profile_from_index("prod")
        mock_set.assert_called_once_with(
            PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, "default,staging"
        )

    @patch("keyring.set_password")
    @patch("keyring.get_password", return_value="default,prod,staging")
    def test_remove_nonexistent_is_noop(self, mock_get, mock_set):
        remove_profile_from_index("missing")
        mock_set.assert_not_called()
```

Run: `uv run pytest tests/test_keyring_store.py::TestProfileIndex -v`
Expected: FAIL — functions don't exist yet.

- [ ] **Step 2: Implement profile index functions**

Add to `src/uipath_mcp/keyring_store.py`:

```python
def list_profiles() -> list[str]:
    """Return a list of all stored profile names."""
    import keyring

    raw = keyring.get_password(PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY)
    if not raw:
        return []
    return [p.strip() for p in raw.split(",") if p.strip()]


def add_profile_to_index(profile: str) -> None:
    """Add a profile name to the index (idempotent)."""
    import keyring

    existing = list_profiles()
    if profile in existing:
        return
    existing.append(profile)
    keyring.set_password(
        PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, ",".join(existing)
    )


def remove_profile_from_index(profile: str) -> None:
    """Remove a profile name from the index (no-op if absent)."""
    import keyring

    existing = list_profiles()
    if profile not in existing:
        return
    existing.remove(profile)
    keyring.set_password(
        PROFILES_INDEX_SERVICE, PROFILES_INDEX_KEY, ",".join(existing)
    )
```

Run: `uv run pytest tests/test_keyring_store.py::TestProfileIndex -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/uipath_mcp/keyring_store.py tests/test_keyring_store.py
git commit -m "feat: add profile index CRUD for keyring"
```

---

### Task 3: Migration from Legacy Single-Tenant Storage

**Files:**
- Modify: `src/uipath_mcp/keyring_store.py`
- Modify: `tests/test_keyring_store.py`

- [ ] **Step 1: Write failing tests for migration**

Add to `tests/test_keyring_store.py`:

```python
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

        with patch("uipath_mcp.keyring_store._get_keyring", return_value=mock_kr):
            result = load_from_keyring(profile="default")

        # Should have read from legacy and returned the values
        assert result["auth_mode"] == "pat"
        assert result["uipath_pat"] == "old_token"

        # Should have written to uipath-mcp/default
        set_calls = {(c.args[0], c.args[1]): c.args[2] for c in mock_kr.set_password.call_args_list}
        assert set_calls[("uipath-mcp/default", "auth_mode")] == "pat"
        assert set_calls[("uipath-mcp/default", "uipath_pat")] == "old_token"

        # Should have deleted legacy entries
        delete_calls = [(c.args[0], c.args[1]) for c in mock_kr.delete_password.call_args_list]
        assert ("uipath-mcp", "auth_mode") in delete_calls

    def test_no_migration_when_default_has_creds(self):
        """If uipath-mcp/default already has credentials, skip migration."""
        data = {
            ("uipath-mcp/default", "auth_mode"): "cloud",
            ("uipath-mcp", "auth_mode"): "pat",  # legacy — should be ignored
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
```

Run: `uv run pytest tests/test_keyring_store.py::TestMigrateLegacyCredentials -v`
Expected: FAIL — migration logic doesn't exist yet.

- [ ] **Step 2: Implement migration in `load_from_keyring`**

Update `load_from_keyring` in `src/uipath_mcp/keyring_store.py`:

```python
def load_from_keyring(profile: str = "default") -> dict[str, Any]:
    """Load all stored credentials from the OS keyring for a given profile.

    Returns a dict of ``{field_name: value}`` for fields that exist.
    Returns an empty dict if the keyring is unavailable or any read fails.

    For the ``"default"`` profile, automatically migrates legacy credentials
    stored under the old ``uipath-mcp`` service name (without profile suffix).
    """
    kr = _get_keyring()
    if kr is None:
        return {}

    svc = service_name_for_profile(profile)
    values: dict[str, Any] = {}
    try:
        for field in KEYRING_FIELDS:
            value = kr.get_password(svc, field)
            if value is not None:
                values[field] = value
    except Exception as exc:
        logger.warning(f"Failed to read from keyring: {exc}. Falling back to env vars.")
        return {}

    # Migrate legacy (un-namespaced) credentials to the "default" profile
    if not values and profile == "default":
        values = _migrate_legacy_credentials(kr)

    if values:
        logger.debug(f"Loaded {len(values)} credential(s) from keyring profile '{profile}'")
    return values


def _migrate_legacy_credentials(kr) -> dict[str, Any]:
    """Migrate credentials from the old uipath-mcp service to uipath-mcp/default."""
    legacy: dict[str, Any] = {}
    try:
        for field in KEYRING_FIELDS:
            value = kr.get_password(SERVICE_NAME, field)
            if value is not None:
                legacy[field] = value
    except Exception:
        return {}

    if not legacy:
        return {}

    logger.debug(f"Migrating {len(legacy)} legacy credential(s) to 'default' profile")
    svc = service_name_for_profile("default")
    try:
        for field, value in legacy.items():
            kr.set_password(svc, field, value)
        add_profile_to_index("default")
        for field in legacy:
            try:
                kr.delete_password(SERVICE_NAME, field)
            except Exception:
                pass
    except Exception as exc:
        logger.warning(f"Migration failed: {exc}")
        return {}

    return legacy
```

Run: `uv run pytest tests/test_keyring_store.py::TestMigrateLegacyCredentials tests/test_keyring_store.py::TestLoadFromKeyringProfile tests/test_keyring_store.py::TestLoadFromKeyring -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/uipath_mcp/keyring_store.py tests/test_keyring_store.py
git commit -m "feat: auto-migrate legacy keyring credentials to default profile"
```

---

### Task 4: CLI `--profile` Flag and `auth list` Command

**Files:**
- Modify: `src/uipath_mcp/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write failing tests for `--profile` on `auth setup`**

Add to `tests/test_cli.py`:

```python
class TestAuthSetupProfile:
    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_setup_with_explicit_profile(self, mock_store, mock_add_index):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "prod"],
            input="https://example.com\nmy_pat\nTestTenant\n\n\nn\n",
        )
        assert result.exit_code == 0, result.output

        # All store_credential calls should use profile="prod"
        for call in mock_store.call_args_list:
            assert call.kwargs.get("profile") == "prod"
        stored_fields = [call.args[0] for call in mock_store.call_args_list]
        assert "auth_mode" in stored_fields
        mock_add_index.assert_called_once_with("prod")

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_setup_auto_derives_profile_name(self, mock_store, mock_add_index):
        """When --profile is omitted, derives name from org/tenant and prompts."""
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat"],
            input="https://example.com\nmy_pat\nMyTenant\n\n\nn\n\n",
        )
        assert result.exit_code == 0, result.output
        # Should have prompted for profile name with auto-derived default
        mock_add_index.assert_called_once()
```

Run: `uv run pytest tests/test_cli.py::TestAuthSetupProfile -v`
Expected: FAIL — `--profile` flag doesn't exist, `_add_profile_to_index` doesn't exist.

- [ ] **Step 2: Write failing tests for read-only prompt in setup**

Add to `tests/test_cli.py`:

```python
class TestAuthSetupReadOnly:
    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_setup_stores_read_only_mode(self, mock_store, mock_add_index):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "readonly-env"],
            input="https://example.com\nmy_pat\nTestTenant\n\n\ny\n",
        )
        assert result.exit_code == 0, result.output
        stored_fields = {call.args[0]: call.args[1] for call in mock_store.call_args_list}
        assert stored_fields.get("read_only_mode") == "true"

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_setup_read_only_defaults_no(self, mock_store, mock_add_index):
        runner = CliRunner()
        result = runner.invoke(
            main,
            ["auth", "setup", "--mode", "pat", "--profile", "rw-env"],
            input="https://example.com\nmy_pat\nTestTenant\n\n\nn\n",
        )
        assert result.exit_code == 0, result.output
        stored_fields = {call.args[0] for call in mock_store.call_args_list}
        assert "read_only_mode" not in stored_fields
```

Run: `uv run pytest tests/test_cli.py::TestAuthSetupReadOnly -v`
Expected: FAIL

- [ ] **Step 3: Write failing tests for `auth test --profile` and `auth clear --profile`**

Add to `tests/test_cli.py`:

```python
class TestAuthTestProfile:
    @patch("uipath_mcp.config.Settings")
    @patch("uipath_mcp.keyring_store.read_all")
    def test_test_with_profile(self, mock_read, mock_settings_cls):
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
        result = runner.invoke(main, ["auth", "test", "--profile", "staging"])
        assert result.exit_code == 0
        mock_read.assert_called_once_with(profile="staging")


class TestAuthClearProfile:
    @patch("uipath_mcp.keyring_store.clear_all", return_value=5)
    @patch("uipath_mcp.cli._remove_profile_from_index")
    def test_clear_with_profile(self, mock_remove, mock_clear):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear", "--profile", "staging", "--yes"])
        assert result.exit_code == 0
        mock_clear.assert_called_once_with(profile="staging")
        mock_remove.assert_called_once_with("staging")
```

Run: `uv run pytest tests/test_cli.py::TestAuthTestProfile tests/test_cli.py::TestAuthClearProfile -v`
Expected: FAIL

- [ ] **Step 4: Write failing test for `auth list`**

Add to `tests/test_cli.py`:

```python
class TestAuthList:
    @patch("uipath_mcp.keyring_store.read_all")
    @patch("uipath_mcp.keyring_store.list_profiles", return_value=["default", "staging"])
    def test_list_shows_profiles(self, mock_list, mock_read):
        mock_read.side_effect = [
            {"auth_mode": "cloud", "uipath_org_name": "myorg", "uipath_tenant_name": "Tenant1"},
            {"auth_mode": "pat", "uipath_tenant_name": "Staging", "read_only_mode": "true"},
        ]
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "list"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "staging" in result.output

    @patch("uipath_mcp.keyring_store.list_profiles", return_value=[])
    def test_list_empty(self, mock_list):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "list"])
        assert "No profiles" in result.output
```

Run: `uv run pytest tests/test_cli.py::TestAuthList -v`
Expected: FAIL

- [ ] **Step 5: Implement all CLI changes**

Replace the entire `src/uipath_mcp/cli.py`:

```python
"""
CLI entry point for the UiPath MCP Server.

Usage::

    uipath-mcp                          Start the MCP server (default profile)
    uipath-mcp --profile prod           Start with the "prod" profile
    uipath-mcp auth setup               Store credentials (auto-derives profile name)
    uipath-mcp auth setup --profile X   Store credentials as profile X
    uipath-mcp auth test  [--profile X] Verify stored credentials
    uipath-mcp auth clear [--profile X] Remove a profile's credentials
    uipath-mcp auth list                List all stored profiles
"""

from __future__ import annotations

import sys

import click


def _add_profile_to_index(profile: str) -> None:
    from .keyring_store import add_profile_to_index
    add_profile_to_index(profile)


def _remove_profile_from_index(profile: str) -> None:
    from .keyring_store import remove_profile_from_index
    remove_profile_from_index(profile)


@click.group(invoke_without_command=True)
@click.option("--profile", default=None, envvar="UIPATH_PROFILE",
              help="Credential profile name (default: UIPATH_PROFILE env var or 'default')")
@click.pass_context
def main(ctx: click.Context, profile: str | None) -> None:
    """UiPath Orchestrator MCP Server."""
    ctx.ensure_object(dict)
    ctx.obj["profile"] = profile
    if ctx.invoked_subcommand is None:
        _start_server(profile=profile)


@main.group()
@click.pass_context
def auth(ctx: click.Context) -> None:
    """Manage credentials stored in the OS keyring."""


@auth.command()
@click.option(
    "--mode",
    type=click.Choice(["cloud", "on_prem", "pat"], case_sensitive=False),
    prompt="Authentication mode",
    help="Authentication mode: cloud, on_prem, or pat",
)
@click.option("--profile", default=None,
              help="Profile name (auto-derived from org/tenant if omitted)")
@click.pass_context
def setup(ctx: click.Context, mode: str, profile: str | None) -> None:
    """Interactive setup: store UiPath credentials in the OS keyring."""
    from rich.console import Console
    from rich.panel import Panel

    from .keyring_store import store_credential

    console = Console()

    # Required fields per auth mode: (field_name, prompt_label, is_secret)
    fields_by_mode: dict[str, list[tuple[str, str, bool]]] = {
        "cloud": [
            ("uipath_client_id", "Client ID", False),
            ("uipath_client_secret", "Client Secret", True),
            ("uipath_org_name", "Organization slug", False),
            ("uipath_tenant_name", "Tenant name", False),
        ],
        "on_prem": [
            ("uipath_base_url", "Orchestrator base URL", False),
            ("uipath_username", "Username", False),
            ("uipath_password", "Password", True),
            ("uipath_tenant_name", "Tenant name", False),
        ],
        "pat": [
            ("uipath_base_url", "Orchestrator base URL", False),
            ("uipath_pat", "Personal Access Token", True),
            ("uipath_tenant_name", "Tenant name", False),
        ],
    }

    optional_fields: list[tuple[str, str]] = [
        ("uipath_folder_id", "Default folder ID"),
        ("uipath_folder_path", "Default folder path"),
    ]

    try:
        # Collect credential values first
        collected: dict[str, str] = {"auth_mode": mode}

        for field_name, label, is_secret in fields_by_mode[mode]:
            value = click.prompt(f"  {label}", hide_input=is_secret)
            collected[field_name] = value

        for field_name, label in optional_fields:
            value = click.prompt(f"  {label} (press Enter to skip)", default="", show_default=False)
            if value:
                collected[field_name] = value

        # Read-only mode prompt
        read_only = click.confirm("  Read-only mode?", default=False)
        if read_only:
            collected["read_only_mode"] = "true"

        # Auto-derive profile name if not given
        if profile is None:
            if mode == "cloud" and "uipath_org_name" in collected:
                derived = f"{collected['uipath_org_name']}/{collected.get('uipath_tenant_name', 'default')}"
            else:
                derived = collected.get("uipath_tenant_name", "default")
            profile = click.prompt("  Profile name", default=derived)

        # Store all collected values
        for field_name, value in collected.items():
            store_credential(field_name, value, profile=profile)

        _add_profile_to_index(profile)

        console.print(
            Panel(
                f"[green]Credentials stored in OS keyring[/green] (profile: {profile})\n"
                f"Auth mode: {mode}\n"
                f"Read-only: {'Yes' if read_only else 'No'}\n\n"
                "[dim]Run [bold]uipath-mcp auth test --profile "
                f"{profile}[/bold] to verify.[/dim]",
                title="Setup Complete",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(f"[red]Failed to store credentials:[/red] {exc}", err=True)
        sys.exit(1)


@auth.command("test")
@click.option("--profile", default="default", help="Profile name to test")
@click.pass_context
def test_cmd(ctx: click.Context, profile: str) -> None:
    """Verify that stored credentials are accessible and valid."""
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table

    from .keyring_store import KEYRING_FIELDS, read_all

    console = Console()

    try:
        stored = read_all(profile=profile)
    except Exception as exc:
        console.print(f"[red]Keyring unavailable:[/red] {exc}", err=True)
        sys.exit(1)

    if not stored:
        console.print(f"[yellow]No credentials found for profile '{profile}'.[/yellow]")
        console.print("Run [bold]uipath-mcp auth setup[/bold] first.")
        sys.exit(1)

    # Display stored fields (mask secrets)
    secret_fields = {"uipath_client_secret", "uipath_password", "uipath_pat"}
    table = Table(title=f"Stored Credentials (profile: {profile})")
    table.add_column("Field", style="cyan")
    table.add_column("Value")
    for field in KEYRING_FIELDS:
        if field in stored:
            display = "****" if field in secret_fields else stored[field]
            table.add_row(field, display)
    console.print(table)

    # Validate by constructing Settings
    try:
        from .config import Settings

        settings = Settings(**stored)
        console.print(
            Panel(
                f"[green]Configuration valid![/green]\n"
                f"Auth mode: {settings.auth_mode.value}\n"
                f"Base URL: {settings.orchestrator_base_url}",
                title="Auth Test Passed",
                border_style="green",
            )
        )
    except Exception as exc:
        console.print(
            Panel(
                f"[red]Configuration invalid:[/red]\n{exc}",
                title="Auth Test Failed",
                border_style="red",
            ),
            err=True,
        )
        sys.exit(1)


@auth.command()
@click.option("--profile", default="default", help="Profile name to clear")
@click.confirmation_option(prompt="Remove all UiPath credentials from this profile?")
def clear(profile: str) -> None:
    """Remove all stored UiPath credentials for a profile from the OS keyring."""
    from rich.console import Console

    from .keyring_store import clear_all

    console = Console()
    try:
        count = clear_all(profile=profile)
        _remove_profile_from_index(profile)
        console.print(f"[green]Cleared {count} credential(s) from profile '{profile}'.[/green]")
    except Exception as exc:
        console.print(f"[red]Failed to clear credentials:[/red] {exc}", err=True)
        sys.exit(1)


@auth.command("list")
def list_cmd() -> None:
    """List all stored credential profiles."""
    from rich.console import Console
    from rich.table import Table

    from .keyring_store import list_profiles, read_all

    console = Console()

    profiles = list_profiles()
    if not profiles:
        console.print("[yellow]No profiles found in keyring.[/yellow]")
        console.print("Run [bold]uipath-mcp auth setup[/bold] to create one.")
        return

    table = Table(title="Credential Profiles")
    table.add_column("Profile", style="cyan")
    table.add_column("Auth Mode")
    table.add_column("Org/Tenant")
    table.add_column("Read-Only")

    for name in profiles:
        data = read_all(profile=name)
        auth_mode = data.get("auth_mode", "?")
        org = data.get("uipath_org_name", "")
        tenant = data.get("uipath_tenant_name", "")
        org_tenant = f"{org} / {tenant}" if org else tenant
        read_only = "Yes" if data.get("read_only_mode") == "true" else "No"
        table.add_row(name, auth_mode, org_tenant, read_only)

    console.print(table)


def _start_server(profile: str | None = None) -> None:
    """Start the MCP server (delegates to server module)."""
    from .config import get_settings
    from .server import mcp

    settings = get_settings(profile=profile)
    kwargs: dict = {}
    if settings.mcp_transport != "stdio":
        kwargs["host"] = settings.mcp_host
        kwargs["port"] = settings.mcp_port
    mcp.run(transport=settings.mcp_transport, **kwargs)
```

Run: `uv run pytest tests/test_cli.py -v`
Expected: Some tests may still fail because `get_settings` doesn't accept `profile` yet — that's Task 5. The `auth setup/test/clear/list` tests should pass.

- [ ] **Step 6: Update existing CLI tests for new behavior**

The existing `TestServerStart` test mocks `_start_server` — it needs to account for the `profile` kwarg now. Update in `tests/test_cli.py`:

```python
class TestServerStart:
    @patch("uipath_mcp.cli._start_server")
    def test_no_args_starts_server(self, mock_start):
        runner = CliRunner()
        runner.invoke(main)
        mock_start.assert_called_once_with(profile=None)


class TestAuthHelp:
    def test_shows_subcommands(self):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "--help"])
        assert "setup" in result.output
        assert "test" in result.output
        assert "clear" in result.output
        assert "list" in result.output
```

The existing `TestAuthSetup` tests need the profile prompt answer appended to input, and the read-only prompt answer. Update:

```python
class TestAuthSetup:
    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_pat_setup_stores_credentials(self, mock_store, mock_add_index):
        runner = CliRunner()
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
        mock_add_index.assert_called_once_with("default")

    @patch("uipath_mcp.cli._add_profile_to_index")
    @patch("uipath_mcp.keyring_store.store_credential")
    def test_cloud_setup_stores_credentials(self, mock_store, mock_add_index):
        runner = CliRunner()
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
```

The existing `TestAuthTest.test_valid_credentials_show_table` needs `read_all` called with `profile=`:

```python
class TestAuthTest:
    @patch("uipath_mcp.keyring_store.read_all")
    def test_no_credentials_exits_1(self, mock_read):
        mock_read.return_value = {}
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "test"])
        assert result.exit_code == 1

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
```

The existing `TestAuthClear`:

```python
class TestAuthClear:
    @patch("uipath_mcp.cli._remove_profile_from_index")
    @patch("uipath_mcp.keyring_store.clear_all", return_value=5)
    def test_clears_with_confirmation(self, mock_clear, mock_remove):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear", "--yes"])
        assert result.exit_code == 0
        mock_clear.assert_called_once_with(profile="default")
        mock_remove.assert_called_once_with("default")
        assert "5" in result.output

    @patch("uipath_mcp.keyring_store.clear_all")
    def test_aborts_without_confirmation(self, mock_clear):
        runner = CliRunner()
        result = runner.invoke(main, ["auth", "clear"])
        mock_clear.assert_not_called()
```

Run: `uv run pytest tests/test_cli.py -v`
Expected: ALL PASS (except `_start_server` test may need `get_settings(profile=)` — handled in Task 5)

- [ ] **Step 7: Commit**

```bash
git add src/uipath_mcp/cli.py tests/test_cli.py
git commit -m "feat: add --profile flag to CLI and auth list command"
```

---

### Task 5: Config `get_settings` Profile Support

**Files:**
- Modify: `src/uipath_mcp/config.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Write failing test for `get_settings(profile=)`**

Add a new file `tests/test_config.py`:

```python
"""Tests for config module profile support."""

from __future__ import annotations

from unittest.mock import patch

from uipath_mcp.config import Settings, get_settings
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
```

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `get_settings` doesn't accept `profile`.

- [ ] **Step 2: Implement profile support in `get_settings`**

In `src/uipath_mcp/config.py`, update `get_settings`:

```python
def get_settings(profile: str | None = None) -> Settings:
    """Return the validated Settings singleton (created on first call).

    Credentials are loaded from the OS keyring first (if available), then
    env vars and ``.env`` fill in any gaps.

    Args:
        profile: Keyring profile name. Resolved as:
                 explicit value → UIPATH_PROFILE env var → "default".
    """
    global _settings
    if _settings is None:
        import os
        from .keyring_store import load_from_keyring

        resolved_profile = profile or os.environ.get("UIPATH_PROFILE", "default")
        keyring_data = load_from_keyring(profile=resolved_profile)

        # If READ_ONLY_MODE env var is set, don't pass keyring's read_only_mode
        # (init kwargs have highest pydantic-settings priority and would override env)
        if os.environ.get("READ_ONLY_MODE") is not None:
            keyring_data.pop("read_only_mode", None)

        _settings = Settings(**keyring_data)
    return _settings
```

Run: `uv run pytest tests/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add src/uipath_mcp/config.py tests/test_config.py
git commit -m "feat: add profile support to get_settings"
```

---

### Task 6: Full Integration Test and Cleanup

**Files:**
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write integration test for server startup with `--profile`**

Add to `tests/test_cli.py`:

```python
class TestServerStartProfile:
    @patch("uipath_mcp.cli._start_server")
    def test_profile_flag_passed_to_server(self, mock_start):
        runner = CliRunner()
        runner.invoke(main, ["--profile", "prod"])
        mock_start.assert_called_once_with(profile="prod")

    @patch("uipath_mcp.cli._start_server")
    def test_no_profile_passes_none(self, mock_start):
        runner = CliRunner()
        runner.invoke(main)
        mock_start.assert_called_once_with(profile=None)
```

Run: `uv run pytest tests/test_cli.py::TestServerStartProfile -v`
Expected: PASS

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli.py
git commit -m "test: add integration tests for --profile server startup"
```

---

### Task 7: Version Bump and Documentation

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`

- [ ] **Step 1: Bump version in `pyproject.toml`**

Update version from `1.2.0` to `1.3.0` (new feature).

Run: `uv run pytest -v` (sanity check)
Expected: ALL PASS

- [ ] **Step 2: Update README with multi-profile usage**

Add a "Multiple Profiles" section to README.md showing:
- `auth setup` with `--profile`
- `auth list`
- `--profile` on server start
- Claude Desktop config example with `--profile`
- `UIPATH_PROFILE` env var

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml README.md
git commit -m "chore: bump version to 1.3.0 and document multi-profile support"
```
