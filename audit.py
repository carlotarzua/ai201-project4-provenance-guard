"""Persistent JSON storage for content decisions and audit events."""

from __future__ import annotations

import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _audit_path() -> Path:
    return Path(os.getenv("AUDIT_LOG_PATH", "data/audit_log.json"))


def _content_path() -> Path:
    return Path(os.getenv("CONTENT_STORE_PATH", "data/content_store.json"))


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path, default: Any) -> Any:
    _ensure_parent(path)
    if not path.exists():
        return deepcopy(default)
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return deepcopy(default)


def _write_json(path: Path, data: Any) -> None:
    _ensure_parent(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    with temp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    temp.replace(path)


def append_audit_event(event: dict[str, Any]) -> dict[str, Any]:
    event = deepcopy(event)
    event.setdefault("timestamp", utc_now())
    with _LOCK:
        path = _audit_path()
        entries = _read_json(path, [])
        if not isinstance(entries, list):
            entries = []
        entries.append(event)
        _write_json(path, entries)
    return event


def get_recent_log(limit: int = 50) -> list[dict[str, Any]]:
    with _LOCK:
        entries = _read_json(_audit_path(), [])
    if not isinstance(entries, list):
        return []
    return entries[-limit:]


def save_content_record(record: dict[str, Any]) -> None:
    content_id = record["content_id"]
    with _LOCK:
        path = _content_path()
        store = _read_json(path, {})
        if not isinstance(store, dict):
            store = {}
        store[content_id] = deepcopy(record)
        _write_json(path, store)


def get_content_record(content_id: str) -> dict[str, Any] | None:
    with _LOCK:
        store = _read_json(_content_path(), {})
    if not isinstance(store, dict):
        return None
    record = store.get(content_id)
    return deepcopy(record) if isinstance(record, dict) else None


def update_content_record(content_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    with _LOCK:
        path = _content_path()
        store = _read_json(path, {})
        if not isinstance(store, dict) or content_id not in store:
            return None
        store[content_id].update(deepcopy(updates))
        _write_json(path, store)
        return deepcopy(store[content_id])
