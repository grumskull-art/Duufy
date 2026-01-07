import sys, os, importlib.util
import logging

import pytest
from httpx import AsyncClient


# Dynamisk import af api.py (fungerer paa Windows og Linux)
api_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "api.py"))
spec = importlib.util.spec_from_file_location("api", api_path)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
app = api.app

logger = logging.getLogger(__name__)


async def _mock_verify_token():
    return {"id": "mock_user"}


async def _stub_list():
    return []


async def _stub_create(data):
    return {"status": "ok", "data": data}


def _install_stubs() -> None:
    api.get_users = _stub_list
    api.create_user = _stub_create
    api.get_groups = _stub_list
    api.get_items = _stub_list
    api.get_history = _stub_list


_install_stubs()


@pytest.fixture(autouse=True)
def _override_auth():
    app.dependency_overrides[api.verify_token] = _mock_verify_token
    yield
    app.dependency_overrides.pop(api.verify_token, None)


@pytest.mark.asyncio
async def test_ping_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/ping")
    assert response.status_code == 200
    logger.info("Endpoint /ping fungerer")


@pytest.mark.asyncio
async def test_users_get_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/users")
    assert response.status_code == 200
    logger.info("Endpoint /users (GET) fungerer")


@pytest.mark.asyncio
async def test_users_post_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/users", json={"navn": "Test"})
    assert response.status_code == 201
    logger.info("Endpoint /users (POST) fungerer")


@pytest.mark.asyncio
async def test_groups_get_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/groups")
    assert response.status_code == 200
    logger.info("Endpoint /groups fungerer")


@pytest.mark.asyncio
async def test_items_get_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/items")
    assert response.status_code == 200
    logger.info("Endpoint /items fungerer")


@pytest.mark.asyncio
async def test_history_get_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/history")
    assert response.status_code == 200
    logger.info("Endpoint /history fungerer")
