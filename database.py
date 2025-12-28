"""Duufy group storage layer.

This module is imported by FastAPI routes. It MUST be safe to import in production.
Therefore: any optional/third‑party backend (e.g. Firestore) is imported lazily.

Public API: legacy function names are preserved (create_group, get_groups, ...)
so the rest of the codebase does not need to change.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from db import safe_read_json, safe_write_json


# ----------------------------
# Configuration
# ----------------------------

_DATA_DIR_DEFAULT = Path("/data") if Path("/data").exists() else Path(__file__).parent / "data"
_JSON_FILE_DEFAULT = _DATA_DIR_DEFAULT / "groups.json"
_ITEMS_FILE_DEFAULT = _DATA_DIR_DEFAULT / "items.json"


def ensure_data_files() -> None:
    data_dir = _JSON_FILE_DEFAULT.parent
    data_dir.mkdir(parents=True, exist_ok=True)

    for file_path in (_JSON_FILE_DEFAULT, _ITEMS_FILE_DEFAULT):
        if not file_path.exists():
            file_path.write_text("[]", encoding="utf-8")
            continue

        content = file_path.read_text(encoding="utf-8")
        if not content.strip():
            file_path.write_text("[]", encoding="utf-8")
            continue

        try:
            json.loads(content)
        except json.JSONDecodeError:
            file_path.write_text("[]", encoding="utf-8")


def load_items() -> List[Dict[str, Any]]:
    file_path = _ITEMS_FILE_DEFAULT
    if not file_path.exists():
        return []

    content = file_path.read_text(encoding="utf-8")
    if not content.strip():
        return []

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []

    if not isinstance(data, list):
        return []
    return data


def save_items(items: List[Dict[str, Any]]) -> None:
    file_path = _ITEMS_FILE_DEFAULT
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_file = file_path.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as f:
        json.dump(items, f, indent=2, ensure_ascii=False)
    temp_file.replace(file_path)


def _get_backend() -> str:
    """Return selected backend.

    Supported values:
      - "json" (default)
      - "firestore"

    Backwards compatibility:
      - USE_LOCAL_JSON=true/false
    """
    backend = os.getenv("DUUFY_STORAGE", "").strip().lower()
    if backend in {"json", "firestore"}:
        return backend

    # Backwards compatibility: default to json unless explicitly disabled
    use_local = os.getenv("USE_LOCAL_JSON", "true").strip().lower()
    if use_local in {"0", "false", "no", "off"}:
        return "firestore"
    return "json"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


# ----------------------------
# Storage interface
# ----------------------------


class GroupStore(Protocol):
    def create_group(self, group_name: str, owner_id: str) -> str:
        ...

    def get_groups(self) -> List[Dict[str, Any]]:
        ...

    def add_member_to_group(self, group_id: str, member_name: str) -> bool:
        ...

    def get_group_members(self, group_id: str) -> List[str]:
        ...

    def get_group_owner(self, group_id: str) -> Optional[str]:
        ...

    def set_active_groups(self, group_ids: List[str]) -> bool:
        ...

    def get_active_groups(self) -> List[str]:
        ...

    def add_item_to_groups(self, item_data: Dict[str, Any], group_ids: Optional[List[str]]) -> bool:
        ...

    def get_group_items(self, group_id: str) -> List[Dict[str, Any]]:
        ...

    def delete_item_from_group(self, group_id: str, item_name: str) -> None:
        ...

    def remove_member_from_group(self, group_id: str, member_name: str) -> bool:
        ...

    def delete_group(self, group_id: str) -> bool:
        ...

    def update_item_quantity(self, group_id: str, item_name: str, new_quantity: str) -> bool:
        ...


# ----------------------------
# JSON implementation
# ----------------------------


@dataclass(frozen=True)
class JsonGroupStore:
    json_file: Path = _JSON_FILE_DEFAULT

    def _load(self) -> Dict[str, Any]:
        data = safe_read_json(self.json_file, {"groups": {}, "active_groups": []})
        if not isinstance(data, dict):
            return {"groups": {}, "active_groups": []}
        return data

    def _save(self, data: Dict[str, Any]) -> None:
        safe_write_json(self.json_file, data)

    @staticmethod
    def _make_group_id(group_name: str) -> str:
        # Stable, URL-friendly group id
        return (
            group_name.strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )

    def create_group(self, group_name: str, owner_id: str) -> str:
        data = self._load()
        group_id = self._make_group_id(group_name)

        if group_id in data["groups"]:
            return group_id

        ts = _now_iso()
        data["groups"][group_id] = {
            "name": group_name.strip(),
            "owner_id": owner_id,
            "members": [owner_id],
            "items": [],
            "created": ts,
            "last_updated": ts,
        }
        self._save(data)
        return group_id

    def get_groups(self) -> List[Dict[str, Any]]:
        data = self._load()
        groups = []
        for gid, g in data.get("groups", {}).items():
            groups.append(
                {
                    "id": gid,
                    "name": g.get("name", gid),
                    "member_count": len(g.get("members", []) or []),
                    "item_count": len(g.get("items", []) or []),
                }
            )
        return groups

    def add_member_to_group(self, group_id: str, member_name: str) -> bool:
        data = self._load()
        if group_id not in data.get("groups", {}):
            return False

        members: List[str] = list(data["groups"][group_id].get("members", []) or [])
        exists = member_name.lower() in {m.lower() for m in members}
        if exists:
            return False

        members.append(member_name)
        data["groups"][group_id]["members"] = members
        data["groups"][group_id]["last_updated"] = _now_iso()
        self._save(data)
        return True

    def get_group_members(self, group_id: str) -> List[str]:
        data = self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return []
        return list(group.get("members", []) or [])

    def get_group_owner(self, group_id: str) -> Optional[str]:
        data = self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return None
        return group.get("owner_id")

    def set_active_groups(self, group_ids: List[str]) -> bool:
        if len(group_ids) > 3:
            return False
        data = self._load()
        data["active_groups"] = list(group_ids)
        self._save(data)
        return True

    def get_active_groups(self) -> List[str]:
        data = self._load()
        return list(data.get("active_groups", []) or [])

    def add_item_to_groups(self, item_data: Dict[str, Any], group_ids: Optional[List[str]]) -> bool:
        data = self._load()
        targets = group_ids or data.get("active_groups", []) or []
        if not targets:
            return False

        item = dict(item_data)
        item["timestamp"] = _now_iso()

        for gid in targets:
            if gid in data.get("groups", {}):
                data["groups"][gid].setdefault("items", []).append(item)
                data["groups"][gid]["last_updated"] = _now_iso()

        self._save(data)
        return True

    def get_group_items(self, group_id: str) -> List[Dict[str, Any]]:
        data = self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return []
        return list(group.get("items", []) or [])

    def delete_item_from_group(self, group_id: str, item_name: str) -> None:
        data = self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return

        items: List[Dict[str, Any]] = list(group.get("items", []) or [])
        for i, item in enumerate(items):
            if (item.get("name", "") or "").lower() == item_name.lower():
                items.pop(i)
                break

        group["items"] = items
        group["last_updated"] = _now_iso()
        self._save(data)

    def remove_member_from_group(self, group_id: str, member_name: str) -> bool:
        data = self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return False

        members: List[str] = list(group.get("members", []) or [])
        new_members = [m for m in members if m.lower() != member_name.lower()]
        group["members"] = new_members
        group["last_updated"] = _now_iso()
        self._save(data)
        return True

    def delete_group(self, group_id: str) -> bool:
        data = self._load()
        if group_id not in data.get("groups", {}):
            return False

        del data["groups"][group_id]
        if group_id in (data.get("active_groups", []) or []):
            data["active_groups"] = [g for g in data["active_groups"] if g != group_id]

        self._save(data)
        return True

    def update_item_quantity(self, group_id: str, item_name: str, new_quantity: str) -> bool:
        data = self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return False

        items: List[Dict[str, Any]] = list(group.get("items", []) or [])
        for item in items:
            if (item.get("name", "") or "").lower() == item_name.lower():
                item["quantity"] = new_quantity
                group["items"] = items
                group["last_updated"] = _now_iso()
                self._save(data)
                return True
        return False


# ----------------------------
# Firestore implementation (lazy import)
# ----------------------------


class FirestoreGroupStore:
    """Firestore backend.

    This is kept minimal; it is only instantiated if selected.
    If you are not using Firestore yet, keep DUUFY_STORAGE=json.
    """

    def __init__(self) -> None:
        try:
            from google.cloud import firestore  # type: ignore
        except ModuleNotFoundError as e:  # pragma: no cover
            raise RuntimeError(
                "DUUFY_STORAGE=firestore selected but google-cloud-firestore is not installed. "
                "Add 'google-cloud-firestore' to requirements.txt or set DUUFY_STORAGE=json."
            ) from e

        self._firestore = firestore
        self._db = firestore.Client()

        # TODO: define collections
        self._groups_col = self._db.collection("groups")
        self._meta_doc = self._db.collection("meta").document("active_groups")

    # NOTE: Below methods are intentionally conservative.
    # If you enable Firestore, you should implement fully or adjust to your data model.
    # For now, we raise a clear error to avoid silent corruption.

    def _not_ready(self) -> None:
        raise NotImplementedError(
            "Firestore backend is selected but not fully implemented for this project yet. "
            "Use DUUFY_STORAGE=json until Firestore implementation is completed."
        )

    def create_group(self, group_name: str, owner_id: str) -> str:
        self._not_ready()

    def get_groups(self) -> List[Dict[str, Any]]:
        self._not_ready()

    def add_member_to_group(self, group_id: str, member_name: str) -> bool:
        self._not_ready()

    def get_group_members(self, group_id: str) -> List[str]:
        self._not_ready()

    def get_group_owner(self, group_id: str) -> Optional[str]:
        self._not_ready()

    def set_active_groups(self, group_ids: List[str]) -> bool:
        self._not_ready()

    def get_active_groups(self) -> List[str]:
        self._not_ready()

    def add_item_to_groups(self, item_data: Dict[str, Any], group_ids: Optional[List[str]]) -> bool:
        self._not_ready()

    def get_group_items(self, group_id: str) -> List[Dict[str, Any]]:
        self._not_ready()

    def delete_item_from_group(self, group_id: str, item_name: str) -> None:
        self._not_ready()

    def remove_member_from_group(self, group_id: str, member_name: str) -> bool:
        self._not_ready()

    def delete_group(self, group_id: str) -> bool:
        self._not_ready()

    def update_item_quantity(self, group_id: str, item_name: str, new_quantity: str) -> bool:
        self._not_ready()


# ----------------------------
# Store factory / singleton
# ----------------------------


_STORE: Optional[GroupStore] = None


def _store() -> GroupStore:
    global _STORE
    if _STORE is not None:
        return _STORE

    backend = _get_backend()
    if backend == "firestore":
        _STORE = FirestoreGroupStore()
    else:
        _STORE = JsonGroupStore(json_file=_JSON_FILE_DEFAULT)
    return _STORE


# ----------------------------
# Legacy function API
# ----------------------------


def create_group(group_name: str, owner_id: str = "Grums") -> str:
    return _store().create_group(group_name, owner_id)


def get_groups() -> List[Dict[str, Any]]:
    return _store().get_groups()


def add_member_to_group(group_id: str, member_name: str) -> bool:
    return _store().add_member_to_group(group_id, member_name)


def get_group_members(group_id: str) -> List[str]:
    return _store().get_group_members(group_id)


def get_group_owner(group_id: str) -> Optional[str]:
    return _store().get_group_owner(group_id)


def set_active_groups(group_ids: List[str]) -> bool:
    return _store().set_active_groups(group_ids)


def get_active_groups() -> List[str]:
    return _store().get_active_groups()


def add_item_to_groups(item_data: Dict[str, Any], group_ids: Optional[List[str]] = None) -> bool:
    return _store().add_item_to_groups(item_data, group_ids)


def get_group_items(group_id: str) -> List[Dict[str, Any]]:
    return _store().get_group_items(group_id)


def delete_item_from_group(group_id: str, item_name: str) -> None:
    return _store().delete_item_from_group(group_id, item_name)


def remove_member_from_group(group_id: str, member_name: str) -> bool:
    return _store().remove_member_from_group(group_id, member_name)


def delete_group(group_id: str) -> bool:
    return _store().delete_group(group_id)


def update_item_quantity(group_id: str, item_name: str, new_quantity: str) -> bool:
    return _store().update_item_quantity(group_id, item_name, new_quantity)
