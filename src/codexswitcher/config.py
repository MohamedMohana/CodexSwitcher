from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

CODEX_HOME = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
AUTH_FILE = Path(os.environ.get("CODEX_AUTH_FILE", CODEX_HOME / "auth.json"))

CODEXSWITCHER_DIR = Path(
    os.environ.get("CODEXSWITCHER_DIR", CODEX_HOME / ".codexswitcher")
)
ACCOUNTS_DIR = CODEXSWITCHER_DIR / "accounts"
BACKUPS_DIR = CODEXSWITCHER_DIR / "backups"
STATE_FILE = CODEXSWITCHER_DIR / ".current"

OLD_SWITCHER_DIR = CODEX_HOME / ".codexswitch"

ACCOUNT_NAME_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"

AUTH_FILE_PERMISSIONS = 0o600
DIR_PERMISSIONS = 0o700


def _migrate_legacy_dir() -> None:
    if not OLD_SWITCHER_DIR.exists() or CODEXSWITCHER_DIR.exists():
        return
    logger.info(
        "Migrating legacy directory %s → %s",
        OLD_SWITCHER_DIR,
        CODEXSWITCHER_DIR,
    )
    shutil.move(str(OLD_SWITCHER_DIR), str(CODEXSWITCHER_DIR))


def ensure_dirs() -> None:
    _migrate_legacy_dir()
    for d in (ACCOUNTS_DIR, BACKUPS_DIR):
        d.mkdir(parents=True, exist_ok=True)
        d.chmod(DIR_PERMISSIONS)


def account_path(name: str) -> Path:
    return ACCOUNTS_DIR / f"{name}.auth.json"


def backup_path(name: str) -> Path:
    return BACKUPS_DIR / f"{name}-backup.auth.json"
