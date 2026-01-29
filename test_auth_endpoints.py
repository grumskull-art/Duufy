import importlib.util
import logging
import os
import sys
import types

import pytest
from httpx import AsyncClient

# Dynamisk import af api.py (fungerer paa Windows og Linux)
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "api.py"))
spec = importlib.util.spec_from_file_location("api", api_path)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
app = api.app


logger = logging.getLogger(__name__)


async def _return_empty_list(*_args, **_kwargs):
    return []


async def _return_empty_dict(*_args, **_kwargs):
    return {}


def _ensure_database_stubs() -> None:
    try:
        import database as db
    except Exception:
        db = types.ModuleType("database")
        sys.modules["database"] = db

    list_funcs = {
        "get_users",
        "get_groups",
        "get_items",
        "get_history",
    }
    dict_funcs = {
        "create_user",
        "update_user",
        "delete_user",
        "create_group",
        "update_group",
        "delete_group",
        "create_item",
        "update_item",
        "delete_item",
        "create_history_entry",
    }

    for name in list_funcs:
        if not hasattr(db, name):
            setattr(db, name, _return_empty_list)
    for name in dict_funcs:
        if not hasattr(db, name):
            setattr(db, name, _return_empty_dict)


_ensure_database_stubs()

from auth import verify_token  # noqa: E402


async def _mock_verify_token():
    return {"id": "mock_user"}


@pytest.mark.asyncio
async def test_ping_open_access():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ping")
    assert response.status_code == 200
    logger.info("Ping endpoint fungerer")


@pytest.mark.asyncio
async def test_users_requires_auth():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/users")
    assert response.status_code == 401
    logger.info("Users endpoint kraever auth")


@pytest.mark.asyncio
async def test_users_with_valid_token():
    app.dependency_overrides[verify_token] = _mock_verify_token
    try:
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.get("/users")
        assert response.status_code == 200
        logger.info("Users endpoint fungerer med gyldig token")
    finally:
        app.dependency_overrides.pop(verify_token, None)
