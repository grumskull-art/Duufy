def _seed_group_state(app_state, client_id="patch-client", active_groups=None):
    active_groups = active_groups or ["g1"]
    app_state["seed_groups"](
        {
            "groups": {
                "g1": {
                    "name": "Hjemme",
                    "owner_id": "u1",
                    "members": ["user@example.com"],
                    "items": [],
                    "created": "2026-01-01T00:00:00",
                    "last_updated": "2026-01-01T00:00:00",
                },
                "g2": {
                    "name": "Sommerhus",
                    "owner_id": "u2",
                    "members": ["other@example.com"],
                    "items": [],
                    "created": "2026-01-01T00:00:00",
                    "last_updated": "2026-01-01T00:00:00",
                },
            },
            "active_groups": [],
            "active_groups_by_client": {client_id: list(active_groups)},
        }
    )


def test_patch_item_success(app_state):
    _seed_group_state(app_state)
    app_state["seed_items"](
        [{"id": "i1", "name": "milk", "quantity": "1", "group_id": "g1"}]
    )
    client = app_state["make_client"](
        {"id": "u1", "email": "user@example.com"}, client_id="patch-client"
    )

    response = client.patch("/items/i1", json={"name": " bread "})

    assert response.status_code == 200
    data = response.json()
    assert data["item"]["name"] == "bread"
    assert data["item"]["quantity"] == "1"


def test_patch_item_empty_body(app_state):
    _seed_group_state(app_state)
    app_state["seed_items"](
        [{"id": "i1", "name": "milk", "quantity": "1", "group_id": "g1"}]
    )
    client = app_state["make_client"](
        {"id": "u1", "email": "user@example.com"}, client_id="patch-client"
    )

    response = client.patch("/items/i1", json={})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_PATCH"


def test_patch_item_not_found(app_state):
    _seed_group_state(app_state)
    app_state["seed_items"](
        [{"id": "i1", "name": "milk", "quantity": "1", "group_id": "g1"}]
    )
    client = app_state["make_client"](
        {"id": "u1", "email": "user@example.com"}, client_id="patch-client"
    )

    response = client.patch("/items/nope", json={"name": "bread"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ITEM_NOT_FOUND"


def test_patch_item_inactive_group(app_state):
    _seed_group_state(app_state)
    app_state["seed_items"](
        [{"id": "i1", "name": "milk", "quantity": "1", "group_id": "g2"}]
    )
    client = app_state["make_client"](
        {"id": "u1", "email": "user@example.com"}, client_id="patch-client"
    )

    response = client.patch("/items/i1", json={"name": "bread"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ITEM_NOT_FOUND"
