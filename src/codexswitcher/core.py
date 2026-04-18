from __future__ import annotations

import contextlib
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path

from codexswitcher import config as cfg
from codexswitcher.auth import copy_auth_atomic, files_match

CODEX_LOGIN_PORT = 1455


class CodexSwitcherError(Exception):
    pass


class InvalidAccountNameError(CodexSwitcherError):
    pass


class AuthFileNotFoundError(CodexSwitcherError):
    pass


class AccountNotFoundError(CodexSwitcherError):
    pass


class AccountAlreadyActiveError(CodexSwitcherError):
    pass


def kill_login_server() -> list[int]:
    killed: list[int] = []
    try:
        result = subprocess.run(
            ["lsof", "-ti", f":{CODEX_LOGIN_PORT}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for pid_str in result.stdout.strip().splitlines():
            pid = int(pid_str.strip())
            if pid != os.getpid():
                with contextlib.suppress(OSError):
                    os.kill(pid, signal.SIGTERM)
                killed.append(pid)
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return killed


def validate_account_name(name: str) -> None:
    if not re.match(cfg.ACCOUNT_NAME_PATTERN, name):
        raise InvalidAccountNameError(
            f"Invalid account name '{name}'. "
            "Use letters, numbers, dots, dashes, or underscores. "
            "Must start with an alphanumeric character."
        )


def _require_auth_file() -> None:
    if not cfg.AUTH_FILE.exists():
        raise AuthFileNotFoundError(
            f"No auth file found at {cfg.AUTH_FILE}. Run 'codex login' first."
        )


def _set_current(name: str) -> None:
    cfg.ensure_dirs()
    cfg.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    cfg.STATE_FILE.write_text(f"{name}\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        cfg.STATE_FILE.chmod(0o600)


def _get_recorded() -> str | None:
    try:
        text = cfg.STATE_FILE.read_text(encoding="utf-8").strip()
        return text or None
    except OSError:
        return None


def _match_live() -> str | None:
    if not cfg.AUTH_FILE.exists():
        return None
    for path in sorted(cfg.account_path("*").parent.glob("*.auth.json")):
        if path.name.endswith("-backup.auth.json"):
            continue
        name = path.name.removesuffix(".auth.json")
        if files_match(cfg.AUTH_FILE, path):
            return name
    return None


@dataclass(frozen=True)
class AccountInfo:
    name: str
    is_active: bool
    is_recorded_only: bool
    summary: str | None


def save_account(name: str) -> Path:
    validate_account_name(name)
    _require_auth_file()
    cfg.ensure_dirs()

    dest = cfg.account_path(name)
    copy_auth_atomic(cfg.AUTH_FILE, dest)
    _set_current(name)
    return dest


def switch_account(name: str) -> Path:
    validate_account_name(name)
    cfg.ensure_dirs()

    source = cfg.account_path(name)
    if not source.exists():
        raise AccountNotFoundError(
            f"Unknown account '{name}'. Run 'codexswitcher list' to see saved accounts."
        )

    matched = _match_live()
    if matched == name:
        _set_current(name)
        raise AccountAlreadyActiveError(f"Account '{name}' is already active.")

    recorded = _get_recorded()
    backup_name = matched or recorded

    if cfg.AUTH_FILE.exists() and backup_name:
        backup_dest = cfg.backup_path(backup_name)
        copy_auth_atomic(cfg.AUTH_FILE, backup_dest)

    copy_auth_atomic(source, cfg.AUTH_FILE)
    _set_current(name)
    return cfg.AUTH_FILE


def list_accounts() -> list[AccountInfo]:
    from codexswitcher.auth import auth_summary

    cfg.ensure_dirs()
    matched = _match_live()
    recorded = _get_recorded()

    accounts: list[AccountInfo] = []
    for path in sorted(cfg.account_path("*").parent.glob("*.auth.json")):
        if path.name.endswith("-backup.auth.json"):
            continue
        name = path.name.removesuffix(".auth.json")
        is_active = name == matched
        is_recorded_only = (
            matched is None and name == recorded
        )
        summary = auth_summary(path)
        accounts.append(
            AccountInfo(
                name=name,
                is_active=is_active,
                is_recorded_only=is_recorded_only,
                summary=summary,
            )
        )
    return accounts


def get_current() -> AccountInfo | None:
    from codexswitcher.auth import auth_summary

    cfg.ensure_dirs()
    matched = _match_live()
    recorded = _get_recorded()

    if matched:
        path = cfg.account_path(matched)
        return AccountInfo(
            name=matched,
            is_active=True,
            is_recorded_only=False,
            summary=auth_summary(path) if path.exists() else None,
        )

    if recorded:
        path = cfg.account_path(recorded)
        return AccountInfo(
            name=recorded,
            is_active=False,
            is_recorded_only=True,
            summary=auth_summary(path) if path.exists() else None,
        )

    return None


def remove_account(name: str) -> Path:
    validate_account_name(name)
    cfg.ensure_dirs()

    source = cfg.account_path(name)
    if not source.exists():
        raise AccountNotFoundError(
            f"Unknown account '{name}'. Run 'codexswitcher list' to see saved accounts."
        )

    source.unlink()

    backup = cfg.backup_path(name)
    if backup.exists():
        backup.unlink()

    if _get_recorded() == name:
        with contextlib.suppress(OSError):
            cfg.STATE_FILE.unlink()

    return source
