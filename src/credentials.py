import json
import os
import sys


def load_credentials(user_id):
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config",
        "users.json",
    )

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Archivo de credenciales no encontrado: {config_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON malformado en {config_path}: {e}")

    users = data.get("users", {})

    if user_id not in users:
        available = ", ".join(users.keys()) if users else "ninguno"
        raise KeyError(
            f"Usuario '{user_id}' no encontrado. Usuarios disponibles: {available}"
        )

    user_data = users[user_id]
    required_keys = ["location", "username", "password"]
    missing = [k for k in required_keys if k not in user_data]
    if missing:
        raise ValueError(
            f"Credenciales incompletas para '{user_id}'. Faltan: {', '.join(missing)}"
        )

    return user_data


def prompt_user_id():
    try:
        user_id = input("Ingrese identificador de usuario: ").strip()
    except EOFError:
        print("Error: No se pudo leer la entrada estandar.")
        sys.exit(1)

    if not user_id:
        print("Error: El identificador de usuario no puede estar vacio.")
        sys.exit(1)

    return user_id
