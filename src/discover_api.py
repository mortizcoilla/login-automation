import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.credentials import load_credentials
from src.browser_automation import run_login, select_date
from src.logger_config import setup_logger


CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "api_config.json",
)


def inject_interceptor(driver):
    driver.execute_script("""
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
            }).catch(function(err) {
                return Promise.reject(err);
            });
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
    """)


def wait_for_api_capture(driver, timeout=15):
    for _ in range(timeout * 10):
        result = driver.execute_script("return window.__capturedApi")
        if result and result.get("response"):
            return result
        time.sleep(0.1)
    return None


def get_headers_from_session(driver):
    cookies = driver.get_cookies()
    cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])

    user_agent = driver.execute_script("return navigator.userAgent")

    return {
        "Cookie": cookie_str,
        "User-Agent": user_agent,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "es-CL,es;q=0.9",
        "Referer": driver.current_url,
    }


def main():
    logger = setup_logger()
    logger.info("=" * 50)
    logger.info("Descubrimiento de API de pacientes iniciado")
    logger.info("=" * 50)

    driver = None
    try:
        user_id = input("Ingrese identificador de usuario: ").strip()
        if not user_id:
            print("Error: El identificador de usuario no puede estar vacio.")
            sys.exit(1)

        credentials = load_credentials(user_id)
        driver = run_login(credentials, logger, headless=False)

        logger.info("Inyectando interceptor de red...")
        inject_interceptor(driver)

        test_date = input("Ingrese fecha de prueba (dd-mm-yyyy) para capturar la API: ").strip()

        logger.info(f"Cambiando a fecha {test_date}...")
        select_date(driver, logger)

        logger.info("Esperando captura de llamada API...")
        captured = wait_for_api_capture(driver)
        if not captured:
            logger.error("No se pudo capturar la llamada API.")
            logger.info("Puede intentar con otra fecha o verificar manualmente.")
            driver.quit()
            sys.exit(1)

        logger.info(f"API capturada: {captured['method']} {captured['url']}")
        logger.info(f"Respuesta contiene {len(captured['response'])} elementos")

        headers = get_headers_from_session(driver)

        body_str = captured.get("body")
        if isinstance(body_str, str):
            try:
                body_str = json.loads(body_str)
            except (json.JSONDecodeError, TypeError):
                pass

        api_config = {
            "url": captured["url"],
            "method": captured["method"],
            "content_type": captured.get("contentType", ""),
            "body_template": body_str,
            "headers": headers,
            "example_response": captured["response"][:3] if captured["response"] else [],
            "total_items_in_example": len(captured["response"]),
        }

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(api_config, f, indent=2, ensure_ascii=False)

        logger.info(f"Configuracion de API guardada en {CONFIG_PATH}")
        print(f"\nAPI descubierta: {captured['method']} {captured['url']}")
        print(f"Elementos en respuesta: {len(captured['response'])}")
        print("Presione Enter para cerrar el navegador...")
        input()

    except Exception as e:
        logger.error(f"Error: {e}")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            logger.info("Navegador cerrado")


if __name__ == "__main__":
    main()
