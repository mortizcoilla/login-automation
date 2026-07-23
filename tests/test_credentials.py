from __future__ import annotations

import json

import pytest

from src import credentials


@pytest.fixture
def tmp_users_json(tmp_path, monkeypatch):
    config_path = tmp_path / "users.json"
    config_path.write_text(
        json.dumps(
            {
                "users": {
                    "alice": {
                        "location": "cesfam_a",
                        "username": "u_alice",
                        "password": "p_alice",
                    },
                    "bob": {
                        "location": "cesfam_b",
                        "username": "u_bob",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(credentials, "_config_path", lambda: str(config_path))
    return config_path


def test_load_credentials_validas(tmp_users_json) -> None:
    creds = credentials.load_credentials("alice")
    assert creds == {
        "location": "cesfam_a",
        "username": "u_alice",
        "password": "p_alice",
    }


def test_load_credentials_inexistente(tmp_users_json) -> None:
    with pytest.raises(KeyError, match="no encontrado"):
        credentials.load_credentials("zoe")


def test_load_credentials_incompletas(tmp_users_json) -> None:
    with pytest.raises(ValueError, match="incompletas"):
        credentials.load_credentials("bob")


def test_load_credentials_json_malformado(tmp_path, monkeypatch) -> None:
    bad = tmp_path / "users.json"
    bad.write_text("not json{", encoding="utf-8")
    monkeypatch.setattr(credentials, "_config_path", lambda: str(bad))
    with pytest.raises(ValueError, match="JSON malformado"):
        credentials.load_credentials("alice")


def test_load_credentials_desde_env(monkeypatch, tmp_users_json) -> None:
    monkeypatch.setenv("USERS_CARLOS_LOCATION", "cesfam_c")
    monkeypatch.setenv("USERS_CARLOS_USERNAME", "u_carlos")
    monkeypatch.setenv("USERS_CARLOS_PASSWORD", "p_carlos")
    creds = credentials.load_credentials("carlos")
    assert creds["username"] == "u_carlos"


def test_env_tiene_prioridad_sobre_json(monkeypatch, tmp_users_json) -> None:
    monkeypatch.setenv("USERS_ALICE_LOCATION", "otro_cesfam")
    monkeypatch.setenv("USERS_ALICE_USERNAME", "otro_user")
    monkeypatch.setenv("USERS_ALICE_PASSWORD", "otra_pass")
    creds = credentials.load_credentials("alice")
    assert creds["location"] == "otro_cesfam"


def test_env_incompleto_cae_a_json(monkeypatch, tmp_users_json) -> None:
    monkeypatch.setenv("USERS_ALICE_PASSWORD", "solo_pass")
    creds = credentials.load_credentials("alice")
    assert creds["password"] == "p_alice"
    assert creds["location"] == "cesfam_a"


def test_list_known_users(monkeypatch, tmp_users_json) -> None:
    monkeypatch.setenv("USERS_DARIA_PASSWORD", "x")
    users = credentials.list_known_users()
    assert "alice" in users
    assert "bob" in users
    assert "daria" in users


def test_prompt_user_id_vacio(monkeypatch) -> None:
    monkeypatch.setattr("builtins.input", lambda _: "")
    with pytest.raises(SystemExit):
        credentials.prompt_user_id()
