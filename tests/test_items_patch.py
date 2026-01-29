from fastapi.testclient import TestClient

import database
import main


def _client_with_data(monkeypatch, tmp_path, items, active_groups):
    items_path = tmp_path / "items.json"
    monkeypatch.setattr(database, "_ITEMS_FILE_DEFAULT", items_path)
    monkeypatch.setattr(
        database,
        "get_active_groups",
        lambda: list(active_groups))
    database.safe_write_json(items_path, items)
    return TestClient(main.app)


def test_patch_item_success(monkeypatch, tmp_path):
    items = [
        {"id": "i1", "name": "milk", "quantity": "1", "group_id": "g1"},
    ]
    client = _client_with_data(monkeypatch, tmp_path, items, ["g1"])
    response = client.patch("/items/i1", json={"name": " bread "})
    assert response.status_code == 200
    data = response.json()
    assert data["item"]["name"] == "bread"
    assert data["item"]["quantity"] == "1"


def test_patch_item_empty_body(monkeypatch, tmp_path):
    items = [
        {"id": "i1", "name": "milk", "quantity": "1", "group_id": "g1"},
    ]
    client = _client_with_data(monkeypatch, tmp_path, items, ["g1"])
    response = client.patch("/items/i1", json={})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_PATCH"


def test_patch_item_not_found(monkeypatch, tmp_path):
    items = [
        {"id": "i1", "name": "milk", "quantity": "1", "group_id": "g1"},
    ]
    client = _client_with_data(monkeypatch, tmp_path, items, ["g1"])
    response = client.patch("/items/nope", json={"name": "bread"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ITEM_NOT_FOUND"


def test_patch_item_inactive_group(monkeypatch, tmp_path):
    items = [
        {"id": "i1", "name": "milk", "quantity": "1", "group_id": "g2"},
    ]
    client = _client_with_data(monkeypatch, tmp_path, items, ["g1"])
    response = client.patch("/items/i1", json={"name": "bread"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ITEM_NOT_FOUND"
