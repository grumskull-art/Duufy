from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

import database
import main


@pytest.fixture
def app_state(monkeypatch, tmp_path):
    monkeypatch.setenv("DUUFY_STORAGE", "json")
    monkeypatch.setattr(database, "_STORE", None)

    groups_path = tmp_path / "groups.json"
    items_path = tmp_path / "items.json"
    invitations_path = tmp_path / "invitations.json"

    monkeypatch.setattr(database, "_JSON_FILE_DEFAULT", groups_path)
    monkeypatch.setattr(database, "_ITEMS_FILE_DEFAULT", items_path)
    monkeypatch.setattr(database, "_INVITATIONS_FILE_DEFAULT", invitations_path)

    database.safe_write_json(
        groups_path,
        {"groups": {}, "active_groups": [], "active_groups_by_client": {}},
    )
    database.safe_write_json(items_path, [])
    database.safe_write_json(invitations_path, [])

    def seed_groups(data):
        database.safe_write_json(groups_path, data)
        monkeypatch.setattr(database, "_STORE", None)

    def seed_items(data):
        database.safe_write_json(items_path, data)

    def seed_invitations(data):
        database.safe_write_json(invitations_path, data)

    def make_client(user: dict, client_id: str = "test-client") -> TestClient:
        async def _override_verify_token():
            return user

        main.app.dependency_overrides[main.verify_token] = _override_verify_token
        return TestClient(
            main.app,
            headers={"X-Duufy-Client-Id": client_id},
        )

    yield {
        "groups_path": groups_path,
        "items_path": items_path,
        "invitations_path": invitations_path,
        "seed_groups": seed_groups,
        "seed_items": seed_items,
        "seed_invitations": seed_invitations,
        "make_client": make_client,
    }

    main.app.dependency_overrides.clear()
    monkeypatch.setattr(database, "_STORE", None)
