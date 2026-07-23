from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

from src.constants import (
    ENV_LOCATION_SUFFIX,
    ENV_PASSWORD_SUFFIX,
    ENV_USER_PREFIX,
    ENV_USERNAME_SUFFIX,
)

load_dotenv()


REQUIRED_KEYS = ("location", "username", "password")


def _config_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "users.json",
    )


def _read_json_users() -> dict[str, dict[str, str]]:
    path = _config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON malformado en {path}: {e}") from e
    users: dict[str, dict[str, str]] = data.get("users", {})
    return users


def _read_env_user(user_id: str) -> dict[str, str] | None:
    prefix = f"{ENV_USER_PREFIX}{user_id.upper()}"
    location = os.getenv(f"{prefix}{ENV_LOCATION_SUFFIX}")
    username = os.getenv(f"{prefix}{ENV_USERNAME_SUFFIX}")
    password = os.getenv(f"{prefix}{ENV_PASSWORD_SUFFIX}")
    if not (location and username and password):
        return None
    return {"location": location, "username": username, "password": password}


def _validate(user_id: str, user_data: dict[str, Any]) -> dict[str, str]:
    missing = [k for k in REQUIRED_KEYS if not user_data.get(k)]
    if missing:
        raise ValueError(f"Credenciales incompletas para '{user_id}'. Faltan: {', '.join(missing)}")
    return {k: str(user_data[k]) for k in REQUIRED_KEYS}


def load_credentials(user_id: str) -> dict[str, str]:
    env_creds = _read_env_user(user_id)
    if env_creds is not None:
        return _validate(user_id, env_creds)

    json_users = _read_json_users()
    if user_id not in json_users:
        available = ", ".join(json_users.keys()) if json_users else "ninguno"
        raise KeyError(
            f"Usuario '{user_id}' no encontrado. "
            f"Usuarios disponibles: {available}. "
            f"Tambien puede definirlo via variables de entorno {ENV_USER_PREFIX}<ID>_*"
        )
    return _validate(user_id, json_users[user_id])


def prompt_user_id(prompt: str = "Ingrese identificador de usuario: ") -> str:
    try:
        user_id = input(prompt).strip()
    except EOFError:
        print("Error: No se pudo leer la entrada estandar.")
        sys.exit(1)
    if not user_id:
        print("Error: El identificador de usuario no puede estar vacio.")
        sys.exit(1)
    return user_id


def list_known_users() -> list[str]:
    env_users = {
        k.removeprefix(ENV_USER_PREFIX).split("_")[0].lower()
        for k in os.environ
        if k.startswith(ENV_USER_PREFIX) and k.endswith(ENV_PASSWORD_SUFFIX)
    }
    json_users = set(_read_json_users().keys())
    return sorted(env_users | json_users)
