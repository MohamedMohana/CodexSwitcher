from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import os
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from codexswitcher.config import AUTH_FILE_PERMISSIONS

EXPIRY_WARNING_SECONDS = 60 * 60 * 24


@dataclass(frozen=True)
class TokenExpiry:
    expired: bool
    expiring_soon: bool
    expires_at: float | None

    @property
    def label(self) -> str:
        if self.expired:
            return "expired"
        if self.expiring_soon:
            return "expiring soon"
        return "valid"


def _decode_jwt_payload(token: str) -> dict | None:
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload = parts[1]
    payload += "=" * (4 - len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def check_token_expiry(path: Path) -> TokenExpiry:
    try:
        data = read_auth(path)
    except (OSError, json.JSONDecodeError):
        return TokenExpiry(expired=False, expiring_soon=False, expires_at=None)

    id_token = data.get("tokens", {}).get("id_token", "")
    if not id_token:
        last_refresh = data.get("last_refresh")
        if last_refresh:
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(last_refresh.replace("Z", "+00:00"))
                expires_at = dt.timestamp() + 3600
            except (ValueError, TypeError):
                return TokenExpiry(expired=False, expiring_soon=False, expires_at=None)
        else:
            return TokenExpiry(expired=False, expiring_soon=False, expires_at=None)
    else:
        claims = _decode_jwt_payload(id_token)
        if not claims or "exp" not in claims:
            return TokenExpiry(expired=False, expiring_soon=False, expires_at=None)
        expires_at = claims["exp"]

    now = time.time()
    expired = now > expires_at
    expiring_soon = not expired and (expires_at - now) < EXPIRY_WARNING_SECONDS
    return TokenExpiry(expired=expired, expiring_soon=expiring_soon, expires_at=expires_at)


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


def auth_summary(path: Path, *, include_expiry: bool = False) -> str | None:
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
    if include_expiry:
        expiry = check_token_expiry(path)
        if expiry.expires_at is not None:
            parts.append(expiry.label)
    return ", ".join(parts)
