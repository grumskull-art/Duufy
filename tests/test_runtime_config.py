import asyncio

import main


def test_allowed_origins_include_mobile_and_public_url(monkeypatch):
    monkeypatch.setenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000, https://duufy.fly.dev/, capacitor://localhost",
    )
    monkeypatch.setattr(main, "PUBLIC_APP_URL", "https://duufy.app/app")

    origins = main._allowed_origins()

    assert "http://localhost:3000" in origins
    assert "https://duufy.fly.dev" in origins
    assert "capacitor://localhost" in origins
    assert "https://duufy.app" in origins


def test_get_config_exposes_public_runtime_flags(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_APP_URL", "https://duufy.app/app")
    monkeypatch.setattr(main, "RESEND_API_KEY", "test-key")
    monkeypatch.setattr(main, "SUPABASE_URL", "https://db.example.supabase.co")
    monkeypatch.setattr(main, "SUPABASE_ANON_KEY", "anon")

    data = asyncio.run(main.get_config())

    assert data["public_app_url"] == "https://duufy.app"
    assert data["invite_email_enabled"] is True
    assert data["supabase_url"] == "https://db.example.supabase.co"


def test_health_reports_runtime_warnings_when_optional_config_missing(monkeypatch):
    monkeypatch.setattr(main, "PUBLIC_APP_URL", "")
    monkeypatch.setattr(main, "RESEND_API_KEY", "")
    main.app.state.supabase_enabled = False

    data = asyncio.run(main.health_check())

    assert data["status"] == "degraded"
    assert data["services"]["email"]["status"] == "degraded"
    assert any("DUUFY_PUBLIC_APP_URL" in warning for warning in data["warnings"])
    assert any("RESEND_API_KEY" in warning for warning in data["warnings"])
