from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

import aiofiles

from db import _cleanup_tmp_files, get_file_lock

"""Duufy group storage layer.

This module is imported by FastAPI routes. It MUST be safe to import in production.
Therefore: any optional/third‑party backend (e.g. Firestore) is imported lazily.

Public API: legacy function names are preserved (create_group, get_groups, ...)
so the rest of the codebase does not need to change.
"""

import os

from dotenv import load_dotenv

# Absolut sti til .env (robust for Codex)
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".env"))
load_dotenv(env_path)

# Miljøstatus (informativ): Supabase er valgfri i lokal/dev mode.
if os.getenv("SUPABASE_URL"):
    print("OK: Supabase konfiguration indlæst.")
else:
    print("INFO: SUPABASE_URL ikke sat. Kører lokal/dev mode.")


logger = logging.getLogger(__name__)


# ----------------------------
# Configuration
# ----------------------------

_DATA_DIR_DEFAULT = (
    Path("/data") if Path("/data").exists() else Path(__file__).parent / "data"
)
_JSON_FILE_DEFAULT = _DATA_DIR_DEFAULT / "groups.json"
_ITEMS_FILE_DEFAULT = _DATA_DIR_DEFAULT / "items.json"


def _rotate_backups(filepath: Path) -> None:
    backup_path = Path(str(filepath) + ".bak")
    backup_1 = Path(str(filepath) + ".bak.1")
    backup_2 = Path(str(filepath) + ".bak.2")

    if backup_2.exists():
        backup_2.unlink()
    if backup_1.exists():
        os.replace(backup_1, backup_2)
    if backup_path.exists():
        os.replace(backup_path, backup_1)


async def ensure_data_files() -> None:
    data_dir = _JSON_FILE_DEFAULT.parent
    data_dir.mkdir(parents=True, exist_ok=True)

    for file_path in (_JSON_FILE_DEFAULT, _ITEMS_FILE_DEFAULT):
        if not file_path.exists():
            await safe_write_json(file_path, [])
            continue

        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()
        except OSError:
            await safe_write_json(file_path, [])
            continue

        if not content.strip():
            await safe_write_json(file_path, [])
            continue

        try:
            await asyncio.to_thread(json.loads, content)
        except json.JSONDecodeError:
            await safe_write_json(file_path, [])


async def _safe_read_json_async(filepath: Path, default: Any = None) -> Any:
    """Thread-safe JSON file reading with file locking"""
    if not filepath.exists():
        return default if default is not None else {}

    lock = await asyncio.to_thread(get_file_lock, filepath)
    await asyncio.to_thread(lock.acquire)
    try:
        await asyncio.to_thread(_cleanup_tmp_files, filepath)
        try:
            async with aiofiles.open(filepath, "r", encoding="utf-8") as f:
                content = await f.read()
            if not content:
                return default if default is not None else {}
            return await asyncio.to_thread(json.loads, content)
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to read JSON file %s: %s", filepath, exc)
            backup_path = Path(str(filepath) + ".bak")
            if backup_path.exists():
                try:
                    async with aiofiles.open(backup_path, "r", encoding="utf-8") as f:
                        content = await f.read()
                    if not content:
                        return default if default is not None else {}
                    return await asyncio.to_thread(json.loads, content)
                except (json.JSONDecodeError, OSError) as backup_exc:
                    logger.warning(
                        "Failed to read JSON backup %s: %s", backup_path, backup_exc
                    )
            return default if default is not None else {}
    finally:
        await asyncio.to_thread(lock.release)


async def _safe_write_json_async(filepath: Path, data: Any) -> None:
    """Thread-safe JSON file writing with file locking"""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lock = await asyncio.to_thread(get_file_lock, filepath)
    await asyncio.to_thread(lock.acquire)
    try:
        await asyncio.to_thread(_cleanup_tmp_files, filepath)
        if filepath.exists():
            await asyncio.to_thread(_rotate_backups, filepath)
            backup_path = Path(str(filepath) + ".bak")
            backup_temp = Path(str(filepath) + f".bak.tmp.{os.getpid()}")
            try:
                await asyncio.to_thread(shutil.copyfile, filepath, backup_temp)
                await asyncio.to_thread(os.replace, backup_temp, backup_path)
            except OSError as exc:
                logger.warning("Failed to update JSON backup %s: %s", backup_path, exc)
                try:
                    if backup_temp.exists():
                        await asyncio.to_thread(backup_temp.unlink)
                except OSError:
                    pass

        temp_file = filepath.with_name(f"{filepath.name}.tmp.{os.getpid()}")
        try:
            payload = await asyncio.to_thread(
                json.dumps, data, indent=2, ensure_ascii=False
            )
            async with aiofiles.open(temp_file, "w", encoding="utf-8") as f:
                await f.write(payload)
                await f.flush()
                fileno = f.fileno()
                await asyncio.to_thread(os.fsync, fileno)
            await asyncio.to_thread(os.replace, temp_file, filepath)
        except OSError as exc:
            logger.error("Failed to write JSON file %s: %s", filepath, exc)
            try:
                if temp_file.exists():
                    await asyncio.to_thread(temp_file.unlink)
            except OSError:
                pass
            raise
    finally:
        await asyncio.to_thread(lock.release)


def safe_read_json(filepath: Path, default: Any = None) -> Any:
    """
    Read JSON with dual sync/async compatibility.

    - In async contexts: returns a coroutine (must be awaited).
    - In sync contexts: executes immediately and returns the value.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_safe_read_json_async(filepath, default))
    return _safe_read_json_async(filepath, default)


def safe_write_json(filepath: Path, data: Any):
    """
    Write JSON with dual sync/async compatibility.

    - In async contexts: returns a coroutine (must be awaited).
    - In sync contexts: executes immediately.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_safe_write_json_async(filepath, data))
    return _safe_write_json_async(filepath, data)


async def load_items() -> List[Dict[str, Any]]:
    data = await safe_read_json(_ITEMS_FILE_DEFAULT, [])
    if not isinstance(data, list):
        return []

    changed = False
    for item in data:
        if isinstance(item, dict) and not item.get("id"):
            item["id"] = uuid4().hex
            changed = True

    if changed:
        await safe_write_json(_ITEMS_FILE_DEFAULT, data)
    return data


async def save_items(items: List[Dict[str, Any]]) -> None:
    await safe_write_json(_ITEMS_FILE_DEFAULT, items)


def _get_backend() -> str:
    """Return selected backend.

    Supported values:
      - "json" (default)
      - "firestore"

    Backwards compatibility:
      - USE_LOCAL_JSON=true/false
    """
    backend = os.getenv("DUUFY_STORAGE", "").strip().lower()
    if backend in {"json", "firestore", "supabase"}:
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
    async def create_group(self, group_name: str, owner_id: str) -> str: ...

    async def get_groups(self) -> List[Dict[str, Any]]: ...

    async def add_member_to_group(self, group_id: str, member_name: str) -> bool: ...

    async def get_group_members(self, group_id: str) -> List[str]: ...

    async def get_group_owner(self, group_id: str) -> Optional[str]: ...

    async def set_active_groups(self, group_ids: List[str]) -> bool: ...

    async def get_active_groups(self) -> List[str]: ...

    async def add_item_to_groups(
        self, item_data: Dict[str, Any], group_ids: Optional[List[str]]
    ) -> bool: ...

    async def get_group_items(self, group_id: str) -> List[Dict[str, Any]]: ...

    async def delete_item_from_group(self, group_id: str, item_name: str) -> None: ...

    async def remove_member_from_group(
        self, group_id: str, member_name: str
    ) -> bool: ...

    async def delete_group(self, group_id: str) -> bool: ...

    async def update_item_quantity(
        self, group_id: str, item_name: str, new_quantity: str
    ) -> bool: ...


# ----------------------------
# JSON implementation
# ----------------------------


@dataclass(frozen=True)
class JsonGroupStore:
    json_file: Path = _JSON_FILE_DEFAULT

    async def _load(self) -> Dict[str, Any]:
        data = await safe_read_json(self.json_file, {"groups": {}, "active_groups": []})
        if not isinstance(data, dict):
            return {"groups": {}, "active_groups": []}
        return data

    async def _save(self, data: Dict[str, Any]) -> None:
        await safe_write_json(self.json_file, data)

    @staticmethod
    def _make_group_id(group_name: str) -> str:
        # Stable, URL-friendly group id
        return group_name.strip().lower().replace(" ", "_").replace("-", "_")

    async def create_group(self, group_name: str, owner_id: str) -> str:
        data = await self._load()
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
        await self._save(data)
        return group_id

    async def get_groups(self) -> List[Dict[str, Any]]:
        data = await self._load()
        items_data = await safe_read_json(_ITEMS_FILE_DEFAULT, [])
        items = items_data if isinstance(items_data, list) else []
        item_counts: Dict[str, int] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            gid = item.get("group_id")
            if not gid:
                continue
            item_counts[gid] = item_counts.get(gid, 0) + 1

        groups = []
        for gid, g in data.get("groups", {}).items():
            groups.append(
                {
                    "id": gid,
                    "name": g.get("name", gid),
                    "member_count": len(g.get("members", []) or []),
                    "item_count": item_counts.get(gid, 0),
                }
            )
        return groups

    async def add_member_to_group(self, group_id: str, member_name: str) -> bool:
        data = await self._load()
        if group_id not in data.get("groups", {}):
            return False

        members: List[str] = list(data["groups"][group_id].get("members", []) or [])
        exists = member_name.lower() in {m.lower() for m in members}
        if exists:
            return False

        members.append(member_name)
        data["groups"][group_id]["members"] = members
        data["groups"][group_id]["last_updated"] = _now_iso()
        await self._save(data)
        return True

    async def get_group_members(self, group_id: str) -> List[str]:
        data = await self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return []
        return list(group.get("members", []) or [])

    async def get_group_owner(self, group_id: str) -> Optional[str]:
        data = await self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return None
        return group.get("owner_id")

    async def set_active_groups(self, group_ids: List[str]) -> bool:
        if len(group_ids) > 3:
            return False
        data = await self._load()
        data["active_groups"] = list(group_ids)
        await self._save(data)
        return True

    async def get_active_groups(self) -> List[str]:
        data = await self._load()
        return list(data.get("active_groups", []) or [])

    async def add_item_to_groups(
        self, item_data: Dict[str, Any], group_ids: Optional[List[str]]
    ) -> bool:
        data = await self._load()
        targets = group_ids or data.get("active_groups", []) or []
        if not targets:
            return False

        item = dict(item_data)
        item["timestamp"] = _now_iso()

        for gid in targets:
            if gid in data.get("groups", {}):
                data["groups"][gid].setdefault("items", []).append(item)
                data["groups"][gid]["last_updated"] = _now_iso()

        await self._save(data)
        return True

    async def get_group_items(self, group_id: str) -> List[Dict[str, Any]]:
        data = await self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return []
        return list(group.get("items", []) or [])

    async def delete_item_from_group(self, group_id: str, item_name: str) -> None:
        data = await self._load()
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
        await self._save(data)

    async def remove_member_from_group(self, group_id: str, member_name: str) -> bool:
        data = await self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return False

        members: List[str] = list(group.get("members", []) or [])
        new_members = [m for m in members if m.lower() != member_name.lower()]
        group["members"] = new_members
        group["last_updated"] = _now_iso()
        await self._save(data)
        return True

    async def delete_group(self, group_id: str) -> bool:
        data = await self._load()
        if group_id not in data.get("groups", {}):
            return False

        del data["groups"][group_id]
        if group_id in (data.get("active_groups", []) or []):
            data["active_groups"] = [g for g in data["active_groups"] if g != group_id]

        await self._save(data)
        return True

    async def update_item_quantity(
        self, group_id: str, item_name: str, new_quantity: str
    ) -> bool:
        data = await self._load()
        group = data.get("groups", {}).get(group_id)
        if not group:
            return False

        items: List[Dict[str, Any]] = list(group.get("items", []) or [])
        for item in items:
            if (item.get("name", "") or "").lower() == item_name.lower():
                item["quantity"] = new_quantity
                group["items"] = items
                group["last_updated"] = _now_iso()
                await self._save(data)
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

    async def create_group(self, group_name: str, owner_id: str) -> str:
        self._not_ready()

    async def get_groups(self) -> List[Dict[str, Any]]:
        self._not_ready()

    async def add_member_to_group(self, group_id: str, member_name: str) -> bool:
        self._not_ready()

    async def get_group_members(self, group_id: str) -> List[str]:
        self._not_ready()

    async def get_group_owner(self, group_id: str) -> Optional[str]:
        self._not_ready()

    async def set_active_groups(self, group_ids: List[str]) -> bool:
        self._not_ready()

    async def get_active_groups(self) -> List[str]:
        self._not_ready()

    async def add_item_to_groups(
        self, item_data: Dict[str, Any], group_ids: Optional[List[str]]
    ) -> bool:
        self._not_ready()

    async def get_group_items(self, group_id: str) -> List[Dict[str, Any]]:
        self._not_ready()

    async def delete_item_from_group(self, group_id: str, item_name: str) -> None:
        self._not_ready()

    async def remove_member_from_group(self, group_id: str, member_name: str) -> bool:
        self._not_ready()

    async def delete_group(self, group_id: str) -> bool:
        self._not_ready()

    async def update_item_quantity(
        self, group_id: str, item_name: str, new_quantity: str
    ) -> bool:
        self._not_ready()


# ----------------------------
# Supabase implementation (lazy import)
# ----------------------------


class SupabaseGroupStore:
    """Supabase PostgreSQL backend via httpx REST API.

    Uses the async CRUD helpers from supabase_client.py.
    Requires SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY in env.
    """

    def __init__(self) -> None:
        # Lazy import to avoid hard dependency when not selected
        from supabase_client import (
            db_insert_async,
            db_delete_async,
            db_request_async,
            db_select_async,
            db_update_async,
        )
        self._insert = db_insert_async
        self._select = db_select_async
        self._update = db_update_async
        self._delete = db_delete_async
        self._request = db_request_async

    @staticmethod
    def _to_uuid_or_none(value: str) -> Optional[str]:
        """Return value if it looks like a UUID, else None."""
        if not value:
            return None
        try:
            from uuid import UUID
            UUID(value)
            return value
        except (ValueError, AttributeError):
            return None

    async def create_group(self, group_name: str, owner_id: str) -> str:
        ts = _now_iso()
        result = await self._insert("groups", {
            "name": group_name.strip(),
            "owner_id": self._to_uuid_or_none(owner_id),
            "created_at": ts,
            "updated_at": ts,
        }, use_service_key=True)

        if result.get("success") and result.get("data"):
            rows = result["data"]
            if isinstance(rows, list) and rows:
                return rows[0]["id"]
        raise RuntimeError(
            f"Failed to create group in Supabase: {result.get('error', 'no data returned')}"
        )

    async def get_groups(self) -> List[Dict[str, Any]]:
        result = await self._select("groups", "*", use_service_key=True)
        if not result.get("success"):
            logger.warning("Failed to fetch groups from Supabase: %s", result.get("error"))
            return []

        groups = []
        for g in result.get("data", []):
            # Count items per group
            items_result = await self._select(
                "items", "id", filters={"group_id": g["id"]}, use_service_key=True
            )
            item_count = len(items_result.get("data", [])) if items_result.get("success") else 0

            # Count members per group
            members_result = await self._select(
                "group_members", "id", filters={"group_id": g["id"]}, use_service_key=True
            )
            member_count = len(members_result.get("data", [])) if members_result.get("success") else 0

            groups.append({
                "id": g["id"],
                "name": g.get("name", ""),
                "member_count": member_count,
                "item_count": item_count,
            })
        return groups

    async def add_member_to_group(self, group_id: str, member_name: str) -> bool:
        # Check if already a member
        existing = await self._select(
            "group_members", "id",
            filters={"group_id": group_id, "user_id": member_name},
            use_service_key=True,
        )
        if existing.get("success") and existing.get("data"):
            return False

        result = await self._insert("group_members", {
            "group_id": group_id,
            "user_id": member_name,
            "role": "member",
        }, use_service_key=True)
        return result.get("success", False)

    async def get_group_members(self, group_id: str) -> List[str]:
        result = await self._select(
            "group_members", "user_id",
            filters={"group_id": group_id},
            use_service_key=True,
        )
        if not result.get("success"):
            return []
        return [row["user_id"] for row in result.get("data", [])]

    async def get_group_owner(self, group_id: str) -> Optional[str]:
        result = await self._select(
            "groups", "owner_id",
            filters={"id": group_id},
            use_service_key=True,
        )
        if result.get("success") and result.get("data"):
            return result["data"][0].get("owner_id")
        return None

    async def set_active_groups(self, group_ids: List[str]) -> bool:
        if len(group_ids) > 3:
            return False
        # Store active groups in local JSON for now (per-device setting)
        await _safe_write_json_async(
            _DATA_DIR_DEFAULT / "active_groups.json", list(group_ids)
        )
        return True

    async def get_active_groups(self) -> List[str]:
        data = await _safe_read_json_async(
            _DATA_DIR_DEFAULT / "active_groups.json", []
        )
        if isinstance(data, list):
            return data
        return []

    async def add_item_to_groups(
        self, item_data: Dict[str, Any], group_ids: Optional[List[str]]
    ) -> bool:
        targets = group_ids or await self.get_active_groups()
        if not targets:
            return False

        ts = _now_iso()
        all_ok = True
        for gid in targets:
            result = await self._insert("items", {
                "group_id": gid,
                "name": item_data.get("name", ""),
                "quantity": str(item_data.get("quantity", "")),
                "unit": item_data.get("unit"),
                "category": item_data.get("category"),
                "checked": False,
                "added_by": item_data.get("added_by"),
                "created_at": ts,
                "updated_at": ts,
            }, use_service_key=True)
            if not result.get("success"):
                logger.warning("Failed to insert item into group %s: %s", gid, result.get("error"))
                all_ok = False
        return all_ok

    async def get_group_items(self, group_id: str) -> List[Dict[str, Any]]:
        result = await self._select(
            "items", "*",
            filters={"group_id": group_id},
            use_service_key=True,
        )
        if not result.get("success"):
            return []
        return result.get("data", [])

    async def delete_item_from_group(self, group_id: str, item_name: str) -> None:
        await self._request(
            "DELETE", "items",
            query_params=f"group_id=eq.{group_id}&name=eq.{item_name}",
            use_service_key=True,
        )

    async def remove_member_from_group(self, group_id: str, member_name: str) -> bool:
        result = await self._request(
            "DELETE", "group_members",
            query_params=f"group_id=eq.{group_id}&user_id=eq.{member_name}",
            use_service_key=True,
        )
        return result.get("success", False)

    async def delete_group(self, group_id: str) -> bool:
        result = await self._delete("groups", "id", group_id, use_service_key=True)
        return result.get("success", False)

    async def update_item_quantity(
        self, group_id: str, item_name: str, new_quantity: str
    ) -> bool:
        result = await self._request(
            "PATCH", "items",
            query_params=f"group_id=eq.{group_id}&name=eq.{item_name}",
            body={"quantity": new_quantity, "updated_at": _now_iso()},
            use_service_key=True,
        )
        return result.get("success", False)


# ----------------------------
# Store factory / singleton
# ----------------------------


_STORE: Optional[GroupStore] = None


def _store() -> GroupStore:
    global _STORE
    if _STORE is not None:
        return _STORE

    backend = _get_backend()
    if backend == "supabase":
        _STORE = SupabaseGroupStore()
    elif backend == "firestore":
        _STORE = FirestoreGroupStore()
    else:
        _STORE = JsonGroupStore(json_file=_JSON_FILE_DEFAULT)
    return _STORE


# ----------------------------
# Legacy function API
# ----------------------------


async def create_group(group_name: str, owner_id: str = "Grums") -> str:
    return await _store().create_group(group_name, owner_id)


async def get_groups() -> List[Dict[str, Any]]:
    return await _store().get_groups()


async def add_member_to_group(group_id: str, member_name: str) -> bool:
    return await _store().add_member_to_group(group_id, member_name)


async def get_group_members(group_id: str) -> List[str]:
    return await _store().get_group_members(group_id)


async def get_group_owner(group_id: str) -> Optional[str]:
    return await _store().get_group_owner(group_id)


async def set_active_groups(group_ids: List[str]) -> bool:
    return await _store().set_active_groups(group_ids)


async def get_active_groups() -> List[str]:
    return await _store().get_active_groups()


async def add_item_to_groups(
    item_data: Dict[str, Any], group_ids: Optional[List[str]] = None
) -> bool:
    return await _store().add_item_to_groups(item_data, group_ids)


async def get_group_items(group_id: str) -> List[Dict[str, Any]]:
    return await _store().get_group_items(group_id)


async def delete_item_from_group(group_id: str, item_name: str) -> None:
    return await _store().delete_item_from_group(group_id, item_name)


async def remove_member_from_group(group_id: str, member_name: str) -> bool:
    return await _store().remove_member_from_group(group_id, member_name)


async def delete_group(group_id: str) -> bool:
    return await _store().delete_group(group_id)


async def update_item_quantity(
    group_id: str, item_name: str, new_quantity: str
) -> bool:
    return await _store().update_item_quantity(group_id, item_name, new_quantity)


# ----------------------------
# Item patch helper (backend-aware)
# ----------------------------


async def patch_item(
    item_id: str, updates: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Patch an item by ID. Returns the updated item or None if not found."""
    backend = _get_backend()

    if backend == "supabase":
        from supabase_client import db_request_async, db_select_async

        # Enforce active group scope: fetch item first, check its group
        active_group_ids = set(await get_active_groups() or [])
        item_result = await db_select_async(
            "items", "*", filters={"id": item_id}, use_service_key=True
        )
        if not item_result.get("success") or not item_result.get("data"):
            return None
        item = item_result["data"][0]
        if item.get("group_id") not in active_group_ids:
            return None

        updates["updated_at"] = _now_iso()
        result = await db_request_async(
            "PATCH", "items",
            query_params=f"id=eq.{item_id}",
            body=updates,
            use_service_key=True,
        )
        if result.get("success") and result.get("data"):
            rows = result["data"]
            if isinstance(rows, list) and rows:
                return rows[0]
        return None

    # JSON backend: load all items, find by id, mutate, save
    items = await load_items()
    active_result = get_active_groups()
    if asyncio.iscoroutine(active_result):
        active_result = await active_result
    active_group_ids = set(active_result or [])

    for item in items:
        if item.get("id") != item_id:
            continue
        if item.get("group_id") not in active_group_ids:
            break

        if "name" in updates:
            item["name"] = str(updates["name"]).strip()
        if "quantity" in updates:
            item["quantity"] = str(updates["quantity"]).strip()

        await save_items(items)
        return item

    return None


# Supabase placeholders


async def get_users() -> dict:
    """Placeholder: Henter brugere fra Supabase"""
    return {"message": "stubbed get_users"}


async def create_user(data: dict) -> dict:
    """Placeholder: Opretter bruger i Supabase"""
    return {"message": "stubbed create_user", "data": data}


async def update_user(user_id: str, data: dict) -> dict:
    """Placeholder: Opdaterer bruger i Supabase"""
    return {"message": "stubbed update_user", "user_id": user_id, "data": data}


async def delete_user(user_id: str) -> dict:
    """Placeholder: Sletter bruger i Supabase"""
    return {"message": "stubbed delete_user", "user_id": user_id}


async def update_group(group_id: str, data: dict) -> dict:
    """Placeholder: Opdaterer gruppe i Supabase"""
    return {"message": "stubbed update_group", "group_id": group_id, "data": data}


async def get_items() -> dict:
    """Placeholder: Henter items fra Supabase"""
    return {"message": "stubbed get_items"}


async def create_item(data: dict) -> dict:
    """Placeholder: Opretter item i Supabase"""
    return {"message": "stubbed create_item", "data": data}


async def update_item(item_id: str, data: dict) -> dict:
    """Placeholder: Opdaterer item i Supabase"""
    return {"message": "stubbed update_item", "item_id": item_id, "data": data}


async def delete_item(item_id: str) -> dict:
    """Placeholder: Sletter item i Supabase"""
    return {"message": "stubbed delete_item", "item_id": item_id}


async def get_history() -> dict:
    """Placeholder: Henter historik fra Supabase"""
    return {"message": "stubbed get_history"}


async def create_history_entry(data: dict) -> dict:
    """Placeholder: Tilfoejer historik i Supabase"""
    return {"message": "stubbed create_history_entry", "data": data}
