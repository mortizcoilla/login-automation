from __future__ import annotations

import json
import sys
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver

from src.api_client import save_api_config
from src.constants import DATE_FORMAT
from src.credentials import load_credentials, prompt_user_id
from src.logger_config import setup_logger

JS_INTERCEPTOR = """
window.__capturedApi = null;

var originalFetch = window.fetch.bind(window);
window.fetch = function() {
    var url = typeof arguments[0] === 'string' ? arguments[0] : arguments[0].url;
    var options = arguments[1] || {};
    var body = options.body || null;

    return originalFetch.apply(this, arguments).then(function(response) {
        var clone = response.clone();
        if (clone.headers.get('content-type') &&
            clone.headers.get('content-type').includes('json')) {
            return clone.json().then(function(data) {
                if (Array.isArray(data) || (data && data.length !== undefined)) {
                    window.__capturedApi = {
                        url: url,
                        method: (options.method || 'GET').toUpperCase(),
                        contentType: options.headers && (options.headers['Content-Type'] || options.headers['content-type']) || '',
                        body: body,
                        response: data
                    };
                }
                return data;
            });
        }
        return response;
    }).catch(function(err) { return Promise.reject(err); });
};

var originalOpen = XMLHttpRequest.prototype.open;
var originalSend = XMLHttpRequest.prototype.send;
XMLHttpRequest.prototype.open = function(method, url) {
    this.__captureMethod = method;
    this.__captureUrl = typeof url === 'string' ? url : url.toString();
    return originalOpen.apply(this, arguments);
};
XMLHttpRequest.prototype.send = function(body) {
    var xhr = this;
    xhr.addEventListener('load', function() {
        try {
            var data = JSON.parse(xhr.responseText);
            if (Array.isArray(data) || (data && data.length !== undefined)) {
                window.__capturedApi = {
                    url: xhr.__captureUrl,
                    method: xhr.__captureMethod,
                    contentType: xhr.getResponseHeader('content-type') || '',
                    body: body || null,
                    response: data
                };
            }
        } catch(e) {}
    });
    return originalSend.apply(this, arguments);
};
"""


def inject_interceptor(driver: WebDriver) -> None:
    driver.execute_script(JS_INTERCEPTOR)


def wait_for_api_capture(driver: WebDriver, timeout: int = 15) -> dict[str, Any] | None:
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        result = driver.execute_script("return window.__capturedApi")
        if result and result.get("response"):
            return result  # type: ignore[no-any-return]
        time.sleep(0.1)
    return None


def get_headers_from_session(driver: WebDriver) -> dict[str, str]:
    cookies = driver.get_cookies()
    cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    user_agent = driver.execute_script("return navigator.userAgent")
    return {
        "Cookie": cookie_str,
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-CL,es;q=0.9",
        "Referer": driver.current_url,
    }


def main() -> int:
    logger = setup_logger()
    logger.info("=" * 50)
    logger.info("Descubrimiento de API de pacientes")
    logger.info("=" * 50)

    from src.browser_automation import run_login, safe_quit, select_date

    driver: WebDriver | None = None
    try:
        user_id = prompt_user_id()
        credentials = load_credentials(user_id)
        driver = run_login(credentials, logger, headless=False)

        logger.info("Inyectando interceptor de red...")
        inject_interceptor(driver)

        test_date = input(f"Ingrese fecha de prueba ({DATE_FORMAT}): ").strip()
        logger.info(f"Cambiando a fecha {test_date}...")
        select_date(driver, logger, fecha_str=test_date)

        logger.info("Esperando captura de API...")
        captured = wait_for_api_capture(driver)
        if not captured:
            logger.error("No se pudo capturar la llamada API.")
            return 1

        logger.info(f"API capturada: {captured['method']} {captured['url']}")
        logger.info(f"Elementos en respuesta: {len(captured['response'])}")

        headers = get_headers_from_session(driver)

        body_str = captured.get("body")
        if isinstance(body_str, str):
            from contextlib import suppress

            with suppress(json.JSONDecodeError, TypeError):
                body_str = json.loads(body_str)

        api_config: dict[str, Any] = {
            "url": captured["url"],
            "method": captured["method"],
            "content_type": captured.get("contentType", ""),
            "body_template": body_str,
            "headers": headers,
            "example_response": captured["response"][:3] if captured["response"] else [],
            "total_items_in_example": len(captured["response"]),
        }
        save_api_config(api_config)
        print(f"\nAPI descubierta: {captured['method']} {captured['url']}")
        print(f"Elementos en respuesta: {len(captured['response'])}")
        print("Presione Enter para cerrar el navegador...")
        input()
        return 0
    except Exception as e:
        logger.error(f"Error: {e}")
        return 1
    finally:
        safe_quit(driver, logger)


if __name__ == "__main__":
    sys.exit(main())
