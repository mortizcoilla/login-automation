from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any
from urllib.parse import quote

import requests
from selenium.webdriver.remote.webdriver import WebDriver

from src.constants import DATE_FORMAT

API_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "api_config.json",
)

DATE_QUERY_FORMAT = "%Y%m%d %H%M%S"
DEFAULT_TIMEOUT = 30
MAX_RETRIES = 3
BACKOFF_BASE = 1.5


def load_api_config(path: str = API_CONFIG_PATH) -> dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No se encuentra {path}. Ejecute primero: python -m src.discover_api"
        )
    with open(path, encoding="utf-8") as f:
        config: dict[str, Any] = json.load(f)
    return config


def save_api_config(config: dict[str, Any], path: str = API_CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def build_url_for_date(template_url: str, date_str: str) -> str:
    try:
        fecha = datetime.strptime(date_str, DATE_FORMAT)
    except ValueError as e:
        raise ValueError(f"Fecha invalida {date_str!r}: {e}") from e

    inicio = fecha.strftime(DATE_QUERY_FORMAT)
    fin = fecha.replace(hour=23, minute=59, second=59).strftime(DATE_QUERY_FORMAT)

    def replace_param(match: re.Match[str]) -> str:
        name = match.group(1)
        if "FechaHoraInicio" in match.group(0):
            return f"{name}={quote(inicio, safe='')}"
        if "FechaHoraTermino" in match.group(0):
            return f"{name}={quote(fin, safe='')}"
        return match.group(0)

    pattern = re.compile(r"([A-Za-z]*FechaHora(?:Inicio|Termino))=([^;]+)")
    return pattern.sub(replace_param, template_url)


def extract_cookies(driver: WebDriver) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for c in driver.get_cookies():
        cookies[c["name"]] = c["value"]
    return cookies


def build_session_from_driver(
    driver: WebDriver,
    extra_headers: dict[str, str] | None = None,
) -> requests.Session:
    session = requests.Session()
    session.cookies.update(extract_cookies(driver))
    user_agent = driver.execute_script("return navigator.userAgent")
    headers: dict[str, str] = {
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-CL,es;q=0.9",
        "Referer": driver.current_url,
    }
    if extra_headers:
        headers.update(extra_headers)
    session.headers.update(headers)
    return session


def _with_retries(fn: Any, *args: Any, retries: int = MAX_RETRIES, **kwargs: Any) -> Any:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return fn(*args, **kwargs)
        except (requests.RequestException, ValueError) as e:
            last_exc = e
            if attempt >= retries:
                break
            wait = BACKOFF_BASE**attempt
            time.sleep(wait)
    assert last_exc is not None
    raise last_exc


def fetch_pacientes_for_date(
    session: requests.Session,
    url_template: str,
    date_str: str,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    url = build_url_for_date(url_template, date_str)

    def _do() -> list[dict[str, Any]]:
        resp = session.get(url, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Respuesta no es lista: {type(data).__name__}")
        return data  # type: ignore[no-any-return]

    result: list[dict[str, Any]] = _with_retries(_do)
    return result
