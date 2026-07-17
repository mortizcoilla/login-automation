import csv
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.credentials import load_credentials
from src.browser_automation import run_login
from src.logger_config import setup_logger

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "config",
    "api_config.json",
)
DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data",
)
CSV_PATH = os.path.join(DATA_DIR, "pacientes_2026.csv")
RAW_DIR = os.path.join(DATA_DIR, "raw_responses")


def load_api_config():
    if not os.path.exists(CONFIG_PATH):
        print("Error: No se encuentra api_config.json. Ejecute primero discover_api.py")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def working_days_to_today():
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end = min(today, datetime(2026, 12, 31))
    start = datetime(2026, 1, 1)
    current = start
    while current <= end:
        if current.weekday() < 5:
            yield current
        current += timedelta(days=1)


def inject_interceptor(driver):
    driver.execute_script("""
        window.__capturedApi = null;

        var nativeOpen = XMLHttpRequest.prototype.open;
        var nativeSend = XMLHttpRequest.prototype.send;

        XMLHttpRequest.prototype.open = function(method, url) {
            this.__method = method;
            this.__url = typeof url === 'string' ? url : (url ? url.toString() : '');
            return nativeOpen.apply(this, arguments);
        };

        XMLHttpRequest.prototype.send = function() {
            var xhr = this;
            xhr.addEventListener('load', function() {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (Array.isArray(data)) {
                        window.__capturedApi = { response: data };
                    }
                } catch(e) {}
            });
            return nativeSend.apply(this, arguments);
        };

        var nativeFetch = window.fetch.bind(window);
        window.fetch = function() {
            var url = typeof arguments[0] === 'string' ? arguments[0] : (arguments[0] ? arguments[0].url : '');
            return nativeFetch.apply(this, arguments).then(function(response) {
                var clone = response.clone();
                if (clone.headers.get('content-type') && clone.headers.get('content-type').includes('json')) {
                    clone.json().then(function(data) {
                        if (Array.isArray(data)) {
                            window.__capturedApi = { response: data };
                        }
                    }).catch(function() {});
                }
                return response;
            });
        };
    """)


def change_date(driver, fecha_str):
    driver.execute_script(
        """
        var input = document.querySelector('input.date-input');
        if (!input) throw new Error('No se encontró input.date-input');

        var nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value'
        ).set;
        nativeSetter.call(input, arguments[0]);

        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        fecha_str,
    )


def wait_for_capture(driver, timeout=5):
    for _ in range(timeout * 10):
        result = driver.execute_script("return window.__capturedApi")
        if result and result.get("response"):
            return result["response"]
        time.sleep(0.1)
    return None


def clear_capture(driver):
    driver.execute_script("window.__capturedApi = null;")


def extract_flat_record(item, date_str):
    obs = item.get("Observacion") or ""
    if obs.strip():
        obs = obs.strip()

    cupos = item.get("Cupos", [])
    citado_por_nombre = ""
    if cupos:
        desc = cupos[0].get("Descripcion", "")
        m = re.search(r"Citado por:\s*(.+)", desc)
        if m:
            citado_por_nombre = m.group(1).strip()

    estado = item.get("EstadoCita", {})
    tipo_atencion = item.get("TipoDeAtencion", {})
    instrumento = item.get("Instrumento", {})
    usuario = item.get("UsuarioAps", {})
    genero = usuario.get("Genero", {})
    prevision = usuario.get("InstitucionPrevisional", {})
    sector = usuario.get("Sector", {})

    return {
        "fecha": date_str,
        "hora_cita": item.get("FechaHora", ""),
        "hora_llegada": item.get("HoraDeLlegada", ""),
        "estado": estado.get("Nombre", ""),
        "nombre_paciente": item.get("NombreUsuarioAps", ""),
        "rut": usuario.get("Rut", ""),
        "numero_ficha": usuario.get("NumeroDeFicha", ""),
        "genero": genero.get("Nombre", ""),
        "sector": sector.get("Nombre", ""),
        "prevision": prevision.get("Nombre", ""),
        "tipo_cupo": item.get("TipoDeCupo", ""),
        "razon": item.get("Razon", ""),
        "tipo_atencion": tipo_atencion.get("Nombre", ""),
        "instrumento": instrumento.get("Codigo", ""),
        "observacion": obs,
        "citado_por": citado_por_nombre,
        "nodo": item.get("Nodo", ""),
        "es_teleconsulta": str(item.get("EsTeleconsulta", False)),
    }


def main():
    logger = setup_logger()
    logger.info("=" * 50)
    logger.info("Extraccion masiva de pacientes 2026 iniciada")
    logger.info("=" * 50)

    config = load_api_config()
    logger.info(f"API: {config['method']} {config['url']}")

    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(RAW_DIR, exist_ok=True)

    driver = None
    try:
        user_id = input("Ingrese identificador de usuario: ").strip()
        if not user_id:
            print("Error: El identificador de usuario no puede estar vacio.")
            sys.exit(1)

        credentials = load_credentials(user_id)
        logger.info("Iniciando sesion...")
        driver = run_login(credentials, logger, headless=False)

        logger.info("Inyectando interceptor de API...")
        inject_interceptor(driver)

        logger.info("Probando con fecha actual...")
        today_str = datetime.now().strftime("%d-%m-%Y")
        change_date(driver, today_str)
        test_data = wait_for_capture(driver)
        if test_data is None:
            logger.error("No se pudo obtener datos de prueba. Saliendo.")
            sys.exit(1)
        logger.info(f"Prueba exitosa: {len(test_data)} registros para hoy")
        clear_capture(driver)

        all_records = []
        total_days = 0
        total_errors = 0
        total_empty = 0

        days = list(working_days_to_today())

        for idx, day in enumerate(days, 1):
            date_str = day.strftime("%d-%m-%Y")
            total_days += 1

            change_date(driver, date_str)
            data = wait_for_capture(driver)

            if data is None:
                total_errors += 1
                if idx == 1 or idx % 50 == 0:
                    logger.info(f"{date_str}: sin respuesta")
                continue

            clear_capture(driver)

            raw_path = os.path.join(RAW_DIR, f"{date_str}.json")
            with open(raw_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            if not data:
                total_empty += 1
            else:
                for item in data:
                    record = extract_flat_record(item, date_str)
                    all_records.append(record)

            if idx % 50 == 0 or idx == len(days):
                logger.info(
                    f"{date_str}: {len(data)} pctes "
                    f"({idx}/{len(days)}, E:{total_errors}, V:{total_empty})"
                )

        if not all_records:
            logger.warning("No se extrajeron registros.")
            sys.exit(0)

        fieldnames = [
            "fecha", "hora_cita", "hora_llegada", "estado",
            "nombre_paciente", "rut", "numero_ficha", "genero",
            "sector", "prevision", "tipo_cupo", "razon",
            "tipo_atencion", "instrumento", "observacion",
            "citado_por", "nodo", "es_teleconsulta",
        ]

        with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(all_records)

        dias_con_datos = len(set(r["fecha"] for r in all_records))
        logger.info("=" * 50)
        logger.info("EXTRACCION COMPLETADA")
        logger.info(f"  Dias procesados:     {total_days}")
        logger.info(f"  Dias con pacientes:  {dias_con_datos}")
        logger.info(f"  Total registros:     {len(all_records)}")
        logger.info(f"  Dias sin datos:      {total_empty}")
        logger.info(f"  Errores:             {total_errors}")
        logger.info(f"  CSV: {CSV_PATH}")
        logger.info("=" * 50)

    except KeyboardInterrupt:
        logger.info("Extraccion interrumpida por el usuario.")
    except Exception as e:
        logger.error(f"Error critico: {e}")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            logger.info("Navegador cerrado")


if __name__ == "__main__":
    main()
