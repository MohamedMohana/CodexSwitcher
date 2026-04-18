from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from codexswitcher.config import AUTH_FILE_PERMISSIONS


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def files_match(a: Path, b: Path) -> bool:
    if not a.exists() or not b.exists():
        return False
    return file_hash(a) == file_hash(b)


def read_auth(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_auth_atomic(data: dict, destination: Path) -> None:
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(parent),
        prefix=".codexswitcher-",
        suffix=".tmp",
    )
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.chmod(tmp_path, AUTH_FILE_PERMISSIONS)
        os.replace(tmp_path, str(destination))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def copy_auth_atomic(source: Path, destination: Path) -> None:
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(parent),
        prefix=".codexswitcher-",
        suffix=".tmp",
    )
    try:
        with open(source, "rb") as src, os.fdopen(tmp_fd, "wb") as dst:
            shutil.copyfileobj(src, dst)
        os.chmod(tmp_path, AUTH_FILE_PERMISSIONS)
        os.replace(tmp_path, str(destination))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)
        raise


def auth_summary(path: Path) -> str | None:
    try:
        data = read_auth(path)
    except (OSError, json.JSONDecodeError):
        return None

    mode = data.get("auth_mode", "unknown")
    tokens = data.get("tokens", {})
    account_id = tokens.get("account_id", "")
    has_api_key = bool(data.get("OPENAI_API_KEY"))

    parts = [f"mode={mode}"]
    if account_id:
        parts.append(f"id={account_id[:8]}...")
    if has_api_key:
        parts.append("api-key=yes")
    return ", ".join(parts)
