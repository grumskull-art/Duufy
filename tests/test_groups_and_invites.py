import main


def test_groups_are_scoped_to_membership_and_trim_active_groups(app_state):
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
            "active_groups_by_client": {"scope-client": ["g1", "g2"]},
        }
    )
    client = app_state["make_client"](
        {"id": "u1", "email": "user@example.com"}, client_id="scope-client"
    )

    response = client.get("/groups")

    assert response.status_code == 200
    data = response.json()
    assert [group["id"] for group in data["groups"]] == ["g1"]
    assert data["active_groups"] == ["g1"]


def test_active_groups_reject_inaccessible_group(app_state):
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
            "active_groups_by_client": {"scope-client": ["g1"]},
        }
    )
    client = app_state["make_client"](
        {"id": "u1", "email": "user@example.com"}, client_id="scope-client"
    )

    response = client.post("/active-groups", json=["g2"])

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "GROUP_ACCESS_DENIED"


def test_invite_flow_accepts_and_activates_group(app_state, monkeypatch):
    monkeypatch.setattr(main, "RESEND_API_KEY", "")
    monkeypatch.setattr(main, "PUBLIC_APP_URL", "https://duufy.example")

    owner_client = app_state["make_client"](
        {"id": "owner-1", "email": "owner@example.com"}, client_id="owner-client"
    )
    created = owner_client.post("/groups/create", json={"name": "Familie"})
    assert created.status_code == 200
    group_id = created.json()["group_id"]

    invite_response = owner_client.post(
        "/invite/send",
        json={"email": "wife@example.com", "group_id": group_id},
    )

    assert invite_response.status_code == 200
    invite_data = invite_response.json()
    assert invite_data["success"] is True
    assert invite_data["email_sent"] is False
    assert invite_data["invite_url"].startswith("https://duufy.example/app?invite=")

    invitations_response = owner_client.get(f"/group/{group_id}/invitations")
    assert invitations_response.status_code == 200
    invitations = invitations_response.json()["invitations"]
    assert len(invitations) == 1

    token = invitations[0]["token"]
    preview_response = owner_client.get(f"/invite/{token}")
    assert preview_response.status_code == 200
    assert preview_response.json()["invitation"]["group_id"] == group_id

    invitee_client = app_state["make_client"](
        {"id": "wife-1", "email": "wife@example.com"}, client_id="invitee-client"
    )
    accept_response = invitee_client.post(f"/invite/{token}/accept")
    assert accept_response.status_code == 200
    assert accept_response.json()["group_id"] == group_id

    groups_response = invitee_client.get("/groups")
    assert groups_response.status_code == 200
    groups_data = groups_response.json()
    assert [group["id"] for group in groups_data["groups"]] == [group_id]
    assert groups_data["active_groups"] == [group_id]


def test_invite_accept_rejects_wrong_email(app_state, monkeypatch):
    monkeypatch.setattr(main, "RESEND_API_KEY", "")
    monkeypatch.setattr(main, "PUBLIC_APP_URL", "https://duufy.example")

    owner_client = app_state["make_client"](
        {"id": "owner-1", "email": "owner@example.com"}, client_id="owner-client"
    )
    group_id = owner_client.post("/groups/create", json={"name": "Familie"}).json()["group_id"]
    token = owner_client.post(
        "/invite/send",
        json={"email": "wife@example.com", "group_id": group_id},
    ).json()["invitation"]["token"]

    stranger_client = app_state["make_client"](
        {"id": "stranger-1", "email": "other@example.com"}, client_id="stranger-client"
    )
    response = stranger_client.post(f"/invite/{token}/accept")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "INVITE_EMAIL_MISMATCH"
