import tomllib
from pathlib import Path


def test_fly_toml_defaults_to_verja_domain():
    fly_toml = tomllib.loads(Path("fly.toml").read_text(encoding="utf-8"))
    env = fly_toml["env"]

    assert env["DUUFY_PUBLIC_APP_URL"] == "https://duufy.verja.dev"
    assert "https://duufy.verja.dev" in env["ALLOWED_ORIGINS"]
