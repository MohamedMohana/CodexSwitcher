from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from codexswitcher import __version__
from codexswitcher.auth import (
    auth_summary,
    copy_auth_atomic,
    file_hash,
    files_match,
    read_auth,
    write_auth_atomic,
)
from codexswitcher.cli import app
from codexswitcher.config import (
    account_path,
    backup_path,
    ensure_dirs,
)
from codexswitcher.core import (
    AccountAlreadyActiveError,
    AccountAlreadyExistsError,
    AccountNotFoundError,
    AuthFileNotFoundError,
    CodexSwitcherError,
    InvalidAccountNameError,
    get_current,
    list_accounts,
    remove_account,
    rename_account,
    save_account,
    switch_account,
    validate_account_name,
)

runner = CliRunner()


@pytest.fixture()
def tmp_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    codex_home = tmp_path / ".codex"
    switch_dir = codex_home / ".codexswitcher"
    auth_file = codex_home / "auth.json"
    accounts_dir = switch_dir / "accounts"
    backups_dir = switch_dir / "backups"
    state_file = switch_dir / ".current"

    monkeypatch.setattr("codexswitcher.config.CODEX_HOME", codex_home)
    monkeypatch.setattr("codexswitcher.config.AUTH_FILE", auth_file)
    monkeypatch.setattr("codexswitcher.config.CODEXSWITCHER_DIR", switch_dir)
    monkeypatch.setattr("codexswitcher.config.ACCOUNTS_DIR", accounts_dir)
    monkeypatch.setattr("codexswitcher.config.BACKUPS_DIR", backups_dir)
    monkeypatch.setattr("codexswitcher.config.STATE_FILE", state_file)

    return {
        "home": codex_home,
        "auth": auth_file,
        "switch_dir": switch_dir,
        "accounts": accounts_dir,
        "backups": backups_dir,
        "state": state_file,
    }


def _write_auth(path: Path, data: dict | None = None) -> None:
    if data is None:
        data = {"auth_mode": "chatgpt", "tokens": {"access_token": "tok123"}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _file_perms(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# ============================================================
# Config tests
# ============================================================


class TestConfig:
    def test_account_path_format(self, tmp_env: dict) -> None:
        assert account_path("work") == tmp_env["accounts"] / "work.auth.json"

    def test_backup_path_format(self, tmp_env: dict) -> None:
        assert backup_path("work") == tmp_env["backups"] / "work-backup.auth.json"

    def test_ensure_dirs_creates_structure(self, tmp_env: dict) -> None:
        ensure_dirs()
        assert tmp_env["accounts"].is_dir()
        assert tmp_env["backups"].is_dir()

    def test_ensure_dirs_idempotent(self, tmp_env: dict) -> None:
        ensure_dirs()
        ensure_dirs()
        assert tmp_env["accounts"].is_dir()

    def test_env_var_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        custom = tmp_path / "custom-codex"
        monkeypatch.setenv("CODEX_HOME", str(custom))
        monkeypatch.setattr("codexswitcher.config.CODEX_HOME", custom)
        monkeypatch.setattr(
            "codexswitcher.config.AUTH_FILE", custom / "auth.json"
        )
        assert (custom / "auth.json") == custom / "auth.json"


# ============================================================
# Auth tests
# ============================================================


class TestFileHash:
    def test_deterministic(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text('{"k": "v"}')
        assert file_hash(p) == file_hash(p)

    def test_returns_hex_string(self, tmp_path: Path) -> None:
        p = tmp_path / "a.json"
        p.write_text("data")
        h = file_hash(p)
        assert all(c in "0123456789abcdef" for c in h)
        assert len(h) == 64

    def test_empty_file(self, tmp_path: Path) -> None:
        p = tmp_path / "empty"
        p.write_bytes(b"")
        h = file_hash(p)
        assert h == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"

    def test_large_file_chunked(self, tmp_path: Path) -> None:
        p = tmp_path / "big.bin"
        data = os.urandom(32_768)
        p.write_bytes(data)
        h = file_hash(p)
        assert len(h) == 64

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_text("hello")
        b.write_text("world")
        assert file_hash(a) != file_hash(b)


class TestFilesMatch:
    def test_same_content(self, tmp_path: Path) -> None:
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        content = '{"x": 1, "y": [2, 3]}'
        a.write_text(content)
        b.write_text(content)
        assert files_match(a, b) is True

    def test_different_content(self, tmp_path: Path) -> None:
        a, b = tmp_path / "a.json", tmp_path / "b.json"
        a.write_text('{"x": 1}')
        b.write_text('{"x": 2}')
        assert files_match(a, b) is False

    def test_first_missing(self, tmp_path: Path) -> None:
        b = tmp_path / "b.json"
        b.write_text("{}")
        assert files_match(tmp_path / "a.json", b) is False

    def test_second_missing(self, tmp_path: Path) -> None:
        a = tmp_path / "a.json"
        a.write_text("{}")
        assert files_match(a, tmp_path / "b.json") is False

    def test_both_missing(self, tmp_path: Path) -> None:
        assert files_match(tmp_path / "a", tmp_path / "b") is False


class TestReadAuth:
    def test_reads_valid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "auth.json"
        p.write_text('{"key": "value", "num": 42}')
        assert read_auth(p) == {"key": "value", "num": 42}

    def test_raises_on_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            read_auth(tmp_path / "nope.json")

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json{{{")
        with pytest.raises(json.JSONDecodeError):
            read_auth(p)


class TestWriteAuthAtomic:
    def test_creates_file_with_content(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.json"
        write_auth_atomic({"hello": "world"}, dest)
        assert dest.exists()
        assert json.loads(dest.read_text()) == {"hello": "world"}

    def test_sets_permissions(self, tmp_path: Path) -> None:
        dest = tmp_path / "perm.json"
        write_auth_atomic({}, dest)
        assert _file_perms(dest) == 0o600

    def test_overwrites_existing(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.json"
        write_auth_atomic({"v": 1}, dest)
        write_auth_atomic({"v": 2}, dest)
        assert json.loads(dest.read_text()) == {"v": 2}

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        dest = tmp_path / "deep" / "nested" / "out.json"
        write_auth_atomic({"ok": True}, dest)
        assert dest.exists()

    def test_no_temp_file_left_on_failure(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.json"
        with patch("json.dump", side_effect=RuntimeError("boom")), pytest.raises(RuntimeError):
            write_auth_atomic({"bad": True}, dest)
        tmp_files = list(tmp_path.glob(".codexswitcher-*"))
        assert len(tmp_files) == 0

    def test_output_has_trailing_newline(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.json"
        write_auth_atomic({"a": 1}, dest)
        content = dest.read_text()
        assert content.endswith("\n")


class TestCopyAuthAtomic:
    def test_preserves_exact_bytes(self, tmp_path: Path) -> None:
        src = tmp_path / "src.json"
        original = '{"compact":true,"nested":{"a":1}}\n'
        src.write_text(original)

        dst = tmp_path / "dst.json"
        copy_auth_atomic(src, dst)
        assert dst.read_text() == original

    def test_sets_permissions(self, tmp_path: Path) -> None:
        src = tmp_path / "src.json"
        src.write_text("{}")
        dst = tmp_path / "dst.json"
        copy_auth_atomic(src, dst)
        assert _file_perms(dst) == 0o600

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        src = tmp_path / "src.json"
        src.write_text("{}")
        dst = tmp_path / "deep" / "dir" / "dst.json"
        copy_auth_atomic(src, dst)
        assert dst.exists()

    def test_no_temp_file_on_failure(self, tmp_path: Path) -> None:
        src = tmp_path / "src.json"
        src.write_text("{}")
        dst = tmp_path / "out.json"
        with patch(
            "shutil.copyfileobj", side_effect=RuntimeError("boom")
        ), pytest.raises(RuntimeError):
            copy_auth_atomic(src, dst)
        tmp_files = list(tmp_path.glob(".codexswitcher-*"))
        assert len(tmp_files) == 0

    def test_binary_identical_to_source(self, tmp_path: Path) -> None:
        src = tmp_path / "src.json"
        src.write_bytes(b'{"key": "value"}')
        dst = tmp_path / "dst.json"
        copy_auth_atomic(src, dst)
        assert src.read_bytes() == dst.read_bytes()


class TestAuthSummary:
    def test_full_summary(self, tmp_path: Path) -> None:
        p = tmp_path / "auth.json"
        _write_auth(p, {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": "sk-abc",
            "tokens": {"account_id": "acct-1234567890"},
        })
        s = auth_summary(p)
        assert "mode=chatgpt" in s
        assert "api-key=yes" in s
        assert "id=acct-123" in s

    def test_minimal_summary(self, tmp_path: Path) -> None:
        p = tmp_path / "auth.json"
        _write_auth(p, {"auth_mode": "api-key"})
        s = auth_summary(p)
        assert s == "mode=api-key"

    def test_missing_file(self, tmp_path: Path) -> None:
        assert auth_summary(tmp_path / "nope.json") is None

    def test_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not json")
        assert auth_summary(p) is None

    def test_no_auth_mode(self, tmp_path: Path) -> None:
        p = tmp_path / "auth.json"
        _write_auth(p, {"tokens": {}})
        s = auth_summary(p)
        assert "mode=unknown" in s

    def test_short_account_id(self, tmp_path: Path) -> None:
        p = tmp_path / "auth.json"
        _write_auth(p, {"auth_mode": "chatgpt", "tokens": {"account_id": "ab"}})
        s = auth_summary(p)
        assert "id=ab..." in s


# ============================================================
# Core — validate_account_name
# ============================================================


class TestValidateAccountName:
    @pytest.mark.parametrize("name", [
        "personal",
        "work",
        "my-account",
        "my_account",
        "my.account",
        "Account123",
        "a",
        "A1",
        "test-123.v2",
    ])
    def test_valid_names(self, name: str) -> None:
        validate_account_name(name)

    @pytest.mark.parametrize("name", [
        "",
        " bad",
        "bad ",
        ".dotstart",
        "-dashstart",
        "has space",
        "has/slash",
        "has\\backslash",
        "name!",
        "name@domain",
        "name#tag",
        "startswith number is ok but 1test is fine",
        "   ",
    ])
    def test_invalid_names(self, name: str) -> None:
        with pytest.raises(InvalidAccountNameError):
            validate_account_name(name)

    def test_error_message_contains_name(self) -> None:
        with pytest.raises(InvalidAccountNameError, match="bad!name"):
            validate_account_name("bad!name")


# ============================================================
# Core — save
# ============================================================


class TestSave:
    def test_creates_snapshot(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        dest = save_account("personal")
        assert dest.exists()
        assert dest == account_path("personal")
        assert read_auth(dest) == read_auth(tmp_env["auth"])

    def test_sets_current(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        assert tmp_env["state"].read_text().strip() == "personal"

    def test_no_auth_file(self, tmp_env: dict) -> None:
        with pytest.raises(AuthFileNotFoundError):
            save_account("personal")

    def test_invalid_name(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        with pytest.raises(InvalidAccountNameError):
            save_account("bad name!")

    def test_overwrites_existing(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"v": 1})
        save_account("work")
        _write_auth(tmp_env["auth"], {"v": 2})
        save_account("work")
        assert read_auth(account_path("work")) == {"v": 2}

    def test_snapshot_permissions(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        dest = save_account("personal")
        assert _file_perms(dest) == 0o600

    def test_snapshot_is_byte_identical_to_source(self, tmp_env: dict) -> None:
        original = json.dumps(
            {"auth_mode": "chatgpt", "tokens": {"access_token": "secret"}},
            separators=(",", ":"),
        )
        tmp_env["auth"].parent.mkdir(parents=True, exist_ok=True)
        tmp_env["auth"].write_text(original)
        dest = save_account("personal")
        assert dest.read_text() == original

    def test_multiple_accounts(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("business")
        assert read_auth(account_path("personal")) == {"account": "A"}
        assert read_auth(account_path("business")) == {"account": "B"}

    def test_save_from_path(self, tmp_env: dict, tmp_path: Path) -> None:
        external = tmp_path / "external.auth.json"
        external.write_text(json.dumps({"imported": True}), encoding="utf-8")

        dest = save_account("imported", source=external)
        assert read_auth(dest) == {"imported": True}

    def test_save_from_path_does_not_touch_state(
        self, tmp_env: dict, tmp_path: Path
    ) -> None:
        _write_auth(tmp_env["auth"])
        save_account("live")
        assert tmp_env["state"].read_text().strip() == "live"

        external = tmp_path / "external.auth.json"
        external.write_text(json.dumps({"imported": True}), encoding="utf-8")
        save_account("imported", source=external)

        # Importing from a file should NOT change which account is active.
        assert tmp_env["state"].read_text().strip() == "live"

    def test_save_from_missing_path(self, tmp_env: dict, tmp_path: Path) -> None:
        missing = tmp_path / "nope.auth.json"
        with pytest.raises(AuthFileNotFoundError):
            save_account("imported", source=missing)


# ============================================================
# Core — switch
# ============================================================


class TestSwitch:
    def test_switch_to_saved_account(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("work")

        switch_account("personal")
        assert read_auth(tmp_env["auth"]) == {"account": "A"}
        assert tmp_env["state"].read_text().strip() == "personal"

    def test_switch_creates_backup(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("work")

        switch_account("personal")
        backup = tmp_env["backups"] / "work-backup.auth.json"
        assert backup.exists()
        assert read_auth(backup) == {"account": "B"}

    def test_switch_unknown_account(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        ensure_dirs()
        with pytest.raises(AccountNotFoundError):
            switch_account("nonexistent")

    def test_switch_already_active(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        with pytest.raises(AccountAlreadyActiveError):
            switch_account("personal")

    def test_round_trip(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("business")

        switch_account("personal")
        assert read_auth(tmp_env["auth"]) == {"account": "A"}

        switch_account("business")
        assert read_auth(tmp_env["auth"]) == {"account": "B"}

        switch_account("personal")
        assert read_auth(tmp_env["auth"]) == {"account": "A"}

    def test_switch_no_backup_when_no_current(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")

        tmp_env["state"].unlink()

        _write_auth(tmp_env["auth"], {"account": "C"})
        ensure_dirs()
        switch_account("personal")
        assert read_auth(tmp_env["auth"]) == {"account": "A"}
        backup_files = list(tmp_env["backups"].glob("*"))
        assert len(backup_files) == 0

    def test_switch_preserves_auth_file_permissions(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("work")

        switch_account("personal")
        assert _file_perms(tmp_env["auth"]) == 0o600

    def test_switch_updates_state(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("alpha")
        _write_auth(tmp_env["auth"], {"b": 2})
        save_account("beta")

        switch_account("alpha")
        assert tmp_env["state"].read_text().strip() == "alpha"

        switch_account("beta")
        assert tmp_env["state"].read_text().strip() == "beta"


# ============================================================
# Core — list
# ============================================================


class TestList:
    def test_empty(self, tmp_env: dict) -> None:
        assert list_accounts() == []

    def test_shows_accounts(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        save_account("work")

        accounts = list_accounts()
        names = [a.name for a in accounts]
        assert "personal" in names
        assert "work" in names

    def test_marks_active(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")

        switch_account("personal")
        accounts = list_accounts()
        active = [a for a in accounts if a.is_active]
        assert len(active) == 1
        assert active[0].name == "personal"

    def test_marks_recorded_only(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        _write_auth(tmp_env["auth"], {"modified": True})

        accounts = list_accounts()
        rec = [a for a in accounts if a.is_recorded_only]
        assert len(rec) == 1
        assert rec[0].name == "personal"

    def test_sorted_alphabetically(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("charlie")
        save_account("alpha")
        save_account("bravo")

        accounts = list_accounts()
        names = [a.name for a in accounts]
        assert names == sorted(names)

    def test_ignores_backup_files(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        ensure_dirs()
        backup_file = tmp_env["backups"] / "personal-backup.auth.json"
        backup_file.write_text("{}")

        accounts = list_accounts()
        names = [a.name for a in accounts]
        assert "personal" in names
        assert "personal-backup" not in names

    def test_account_info_has_summary(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {
            "auth_mode": "chatgpt",
            "tokens": {"account_id": "acct-xyz"},
        })
        save_account("work")
        accounts = list_accounts()
        assert accounts[0].summary is not None
        assert "chatgpt" in accounts[0].summary

    def test_ignores_backup_auth_json_in_glob(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        _write_auth(tmp_env["auth"], {"other": True})
        save_account("work")

        ensure_dirs()
        (tmp_env["accounts"] / "personal-backup.auth.json").write_text("{}")

        accounts = list_accounts()
        names = [a.name for a in accounts]
        assert "personal" in names
        assert "work" in names
        assert "personal-backup" not in names


# ============================================================
# Core — current
# ============================================================


class TestCurrent:
    def test_none(self, tmp_env: dict) -> None:
        assert get_current() is None

    def test_active(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        info = get_current()
        assert info is not None
        assert info.name == "personal"
        assert info.is_active is True
        assert info.is_recorded_only is False

    def test_recorded_only(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        _write_auth(tmp_env["auth"], {"modified": True})
        info = get_current()
        assert info is not None
        assert info.name == "personal"
        assert info.is_recorded_only is True
        assert info.is_active is False

    def test_has_summary(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"auth_mode": "api-key"})
        save_account("work")
        info = get_current()
        assert info is not None
        assert info.summary is not None
        assert "api-key" in info.summary

    def test_after_switch(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"b": 2})
        save_account("business")
        switch_account("personal")
        info = get_current()
        assert info is not None
        assert info.name == "personal"
        assert info.is_active is True

    def test_no_state_file(self, tmp_env: dict) -> None:
        ensure_dirs()
        assert get_current() is None

    def test_empty_state_file(self, tmp_env: dict) -> None:
        ensure_dirs()
        tmp_env["state"].parent.mkdir(parents=True, exist_ok=True)
        tmp_env["state"].write_text("   \n")
        assert get_current() is None


# ============================================================
# Core — remove
# ============================================================


class TestRemove:
    def test_deletes_snapshot(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        remove_account("personal")
        assert not account_path("personal").exists()

    def test_unknown(self, tmp_env: dict) -> None:
        ensure_dirs()
        with pytest.raises(AccountNotFoundError):
            remove_account("ghost")

    def test_clears_state(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        remove_account("personal")
        assert not tmp_env["state"].exists()

    def test_cleans_backup(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")
        switch_account("personal")
        remove_account("work")
        assert not (tmp_env["backups"] / "work-backup.auth.json").exists()

    def test_does_not_clear_state_for_other_account(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        _write_auth(tmp_env["auth"], {"other": True})
        save_account("work")
        remove_account("personal")
        assert tmp_env["state"].exists()
        assert tmp_env["state"].read_text().strip() == "work"

    def test_returns_deleted_path(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        result = remove_account("personal")
        assert result == account_path("personal")

    def test_invalid_name(self, tmp_env: dict) -> None:
        with pytest.raises(InvalidAccountNameError):
            remove_account("bad!name")


# ============================================================
# Core — rename
# ============================================================


class TestRename:
    def test_renames_snapshot(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        rename_account("personal", "work")
        assert not account_path("personal").exists()
        assert account_path("work").exists()

    def test_updates_state_file(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        rename_account("personal", "work")
        assert tmp_env["state"].read_text().strip() == "work"

    def test_moves_backup(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")
        switch_account("personal")
        rename_account("work", "business")
        assert (tmp_env["backups"] / "business-backup.auth.json").exists()
        assert not (tmp_env["backups"] / "work-backup.auth.json").exists()

    def test_unknown(self, tmp_env: dict) -> None:
        ensure_dirs()
        with pytest.raises(AccountNotFoundError):
            rename_account("ghost", "new")

    def test_destination_exists(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")
        with pytest.raises(AccountAlreadyExistsError):
            rename_account("personal", "work")

    def test_same_name_rejected(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        with pytest.raises(InvalidAccountNameError):
            rename_account("personal", "personal")

    def test_invalid_new_name(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        with pytest.raises(InvalidAccountNameError):
            rename_account("personal", "bad!name")

    def test_other_accounts_state_untouched(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")
        rename_account("personal", "home")
        assert tmp_env["state"].read_text().strip() == "work"


# ============================================================
# Core — error hierarchy
# ============================================================


class TestErrorHierarchy:
    def test_all_errors_inherit_from_base(self) -> None:
        assert issubclass(InvalidAccountNameError, CodexSwitcherError)
        assert issubclass(AuthFileNotFoundError, CodexSwitcherError)
        assert issubclass(AccountNotFoundError, CodexSwitcherError)
        assert issubclass(AccountAlreadyActiveError, CodexSwitcherError)

    def test_base_inherits_from_exception(self) -> None:
        assert issubclass(CodexSwitcherError, Exception)


# ============================================================
# CLI tests
# ============================================================


class TestCLIHelp:
    def test_help(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "codex" in result.output.lower()
        assert "switch" in result.output.lower()

    def test_version(self) -> None:
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_version_short(self) -> None:
        result = runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        assert result.exit_code != 0
        assert "Usage" in result.output or "usage" in result.output


class TestCLISave:
    def test_save_success(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        result = runner.invoke(app, ["save", "personal"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert account_path("personal").exists()

    def test_save_no_auth_file(self, tmp_env: dict) -> None:
        result = runner.invoke(app, ["save", "personal"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_save_invalid_name(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        result = runner.invoke(app, ["save", "bad name!"])
        assert result.exit_code == 1
        assert "Error" in result.output


class TestCLIUse:
    def test_switch_by_name(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("business")

        result = runner.invoke(app, ["use", "personal"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert read_auth(tmp_env["auth"]) == {"account": "A"}

    def test_switch_already_active(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")

        result = runner.invoke(app, ["use", "personal"])
        assert result.exit_code == 0
        assert "already active" in result.output

    def test_switch_unknown_account(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        ensure_dirs()
        result = runner.invoke(app, ["use", "nonexistent"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_interactive_no_accounts(self, tmp_env: dict) -> None:
        ensure_dirs()
        result = runner.invoke(app, ["use"], input="1\n")
        assert result.exit_code == 1
        assert "No saved accounts" in result.output

    def test_interactive_picker_by_number(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("business")
        switch_account("personal")

        result = runner.invoke(app, ["use"], input="business\n")
        assert result.exit_code == 0
        assert read_auth(tmp_env["auth"]) == {"account": "B"}

    def test_interactive_picker_by_name(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"account": "A"})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"account": "B"})
        save_account("business")
        switch_account("personal")

        result = runner.invoke(app, ["use"], input="business\n")
        assert result.exit_code == 0
        assert read_auth(tmp_env["auth"]) == {"account": "B"}


class TestCLIList:
    def test_empty(self, tmp_env: dict) -> None:
        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "No saved" in result.output

    def test_shows_accounts(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        save_account("business")

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert "business" in result.output

    def test_shows_active_marker(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")
        switch_account("personal")

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "* active" in result.output

    def test_shows_recorded_marker(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        _write_auth(tmp_env["auth"], {"modified": True})

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "~" in result.output

    def test_json_empty(self, tmp_env: dict) -> None:
        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        assert json.loads(result.output) == []

    def test_json_payload(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"a": 1})
        save_account("personal")
        _write_auth(tmp_env["auth"], {"a": 2})
        save_account("work")
        switch_account("personal")

        result = runner.invoke(app, ["list", "--json"])
        assert result.exit_code == 0
        payload = json.loads(result.output)
        by_name = {item["name"]: item for item in payload}
        assert by_name["personal"]["is_active"] is True
        assert by_name["work"]["is_active"] is False
        assert "name" in by_name["personal"]
        assert "summary" in by_name["personal"]
        assert "recorded" in result.output


class TestCLICurrent:
    def test_no_accounts(self, tmp_env: dict) -> None:
        result = runner.invoke(app, ["current"])
        assert result.exit_code == 0
        assert "No saved accounts" in result.output

    def test_active_account(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")

        result = runner.invoke(app, ["current"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert "active" in result.output

    def test_recorded_only(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        _write_auth(tmp_env["auth"], {"modified": True})

        result = runner.invoke(app, ["current"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert "differs" in result.output

    def test_unlinked_auth(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")
        save_account("business")
        _write_auth(tmp_env["auth"], {"totally": "different"})

        result = runner.invoke(app, ["current"])
        assert result.exit_code == 0


class TestCLIRemove:
    def test_remove_success(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")

        result = runner.invoke(app, ["remove", "personal", "-y"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert not account_path("personal").exists()

    def test_remove_unknown(self, tmp_env: dict) -> None:
        ensure_dirs()
        result = runner.invoke(app, ["remove", "ghost", "-y"])
        assert result.exit_code == 1
        assert "Error" in result.output

    def test_remove_with_confirmation_yes(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")

        result = runner.invoke(app, ["remove", "personal"], input="y\n")
        assert result.exit_code == 0
        assert not account_path("personal").exists()

    def test_remove_with_confirmation_no(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"])
        save_account("personal")

        result = runner.invoke(app, ["remove", "personal"], input="n\n")
        assert result.exit_code == 0
        assert "Cancelled" in result.output
        assert account_path("personal").exists()


# ============================================================
# Integration / end-to-end tests
# ============================================================


class TestEndToEnd:
    def test_full_workflow(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"user": "alice", "org": "personal"})
        save_account("personal")

        _write_auth(tmp_env["auth"], {"user": "bob", "org": "business"})
        save_account("business")

        accounts = list_accounts()
        assert len(accounts) == 2
        active = [a for a in accounts if a.is_active]
        assert active[0].name == "business"

        switch_account("personal")
        info = get_current()
        assert info is not None
        assert info.name == "personal"
        assert info.is_active is True
        assert read_auth(tmp_env["auth"]) == {"user": "alice", "org": "personal"}

        switch_account("business")
        info = get_current()
        assert info is not None
        assert info.name == "business"
        assert read_auth(tmp_env["auth"]) == {"user": "bob", "org": "business"}

        remove_account("personal")
        accounts = list_accounts()
        assert len(accounts) == 1
        assert accounts[0].name == "business"

    def test_cli_full_workflow(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"user": "alice"})
        runner.invoke(app, ["save", "personal"])
        assert account_path("personal").exists()

        _write_auth(tmp_env["auth"], {"user": "bob"})
        runner.invoke(app, ["save", "work"])
        assert account_path("work").exists()

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "personal" in result.output
        assert "work" in result.output

        result = runner.invoke(app, ["use", "personal"])
        assert result.exit_code == 0
        assert read_auth(tmp_env["auth"]) == {"user": "alice"}

        result = runner.invoke(app, ["current"])
        assert result.exit_code == 0
        assert "personal" in result.output

        result = runner.invoke(app, ["use", "work"])
        assert result.exit_code == 0
        assert read_auth(tmp_env["auth"]) == {"user": "bob"}

        result = runner.invoke(app, ["remove", "personal", "-y"])
        assert result.exit_code == 0
        assert not account_path("personal").exists()

        result = runner.invoke(app, ["list"])
        assert result.exit_code == 0
        assert "personal" not in result.output
        assert "work" in result.output

    def test_three_accounts_round_robin(self, tmp_env: dict) -> None:
        _write_auth(tmp_env["auth"], {"id": 1})
        save_account("alpha")
        _write_auth(tmp_env["auth"], {"id": 2})
        save_account("beta")
        _write_auth(tmp_env["auth"], {"id": 3})
        save_account("gamma")

        for expected_name, expected_data in [
            ("alpha", {"id": 1}),
            ("beta", {"id": 2}),
            ("gamma", {"id": 3}),
            ("alpha", {"id": 1}),
            ("gamma", {"id": 3}),
        ]:
            switch_account(expected_name)
            assert read_auth(tmp_env["auth"]) == expected_data
            info = get_current()
            assert info is not None
            assert info.name == expected_name
