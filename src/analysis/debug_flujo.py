"""Debug: ejecuta el flujo login + clicks (menú → Box → Pacientes citados).

NO sigue con select_date ni listar_iniciados. Solo valida que los 3
clicks funcionan y la página de Pacientes citados queda cargada.

Si funciona, debe terminar con:
  run_login OK — URL final: https://clinico.rayenaps.cl/some-path
  Y una screenshot step_3_pacientes_citados_*.png mostrando la página
  con la tabla de citados y el input.date-input.

Si falla, captura el estado para diagnóstico.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger


def main() -> int:
    logger = setup_logger()
    print("=" * 60)
    print("DEBUG: Flujo de login + navegación a Pacientes citados")
    print("=" * 60)

    users = list_known_users()
    if not users:
        print("ERROR: no hay usuarios configurados", file=sys.stderr)
        return 1
    user_id = users[0]
    print(f"Usando user: '{user_id}'")

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    from src.browser_automation import (
        _capture_after_click,
        _wait_loading_modal_gone,
        run_login,
        safe_quit,
    )

    driver = None
    try:
        driver = run_login(credentials, logger, headless=False)
        print(f"\n>>> run_login OK. URL: {driver.current_url}")

        # Después de run_login, capturar estado final
        _capture_after_click(driver, logger, "4_final_state")

        # Verificar que el date input existe
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support import expected_conditions as EC  # noqa: N812
        from selenium.webdriver.support.ui import WebDriverWait

        try:
            date_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input.date-input"))
            )
            print(f">>> date input ENCONTRADO. Tag: {date_input.tag_name}")
        except Exception as e:  # noqa: BLE001
            print(f">>> date input NO encontrado en 10s: {e}")
            # Capturar HTML para diagnóstico
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = f"debug_state_{ts}.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(driver.page_source[:200000])
            print(f">>> HTML guardado en: {html_path}")

        # Buscar el ícono de calendario por si es lo que vale
        icon_count = len(
            driver.find_elements(By.CSS_SELECTOR, "i.fal.fa-calendar-day")
        )
        print(f">>> Iconos 'fal fa-calendar-day' encontrados: {icon_count}")

        # Listar todos los inputs visibles
        all_inputs = driver.find_elements(By.CSS_SELECTOR, "input")
        print(f">>> Total de inputs en la página: {len(all_inputs)}")
        for i, inp in enumerate(all_inputs[:20]):
            try:
                placeholder = inp.get_attribute("placeholder") or ""
                input_type = inp.get_attribute("type") or ""
                cls = inp.get_attribute("class") or ""
                visible = inp.is_displayed()
                print(
                    f"    [{i}] type={input_type} class='{cls[:40]}' "
                    f"placeholder='{placeholder[:30]}' visible={visible}"
                )
            except Exception as e:  # noqa: BLE001
                print(f"    [{i}] error leyendo: {e}")

        print()
        print("=" * 60)
        print("FIN DEBUG. Enter para cerrar el browser...")
        print("=" * 60)
        try:
            input()
        except EOFError:
            pass
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error: {e}")
        return 1
    finally:
        safe_quit(driver, logger)


if __name__ == "__main__":
    sys.exit(main())
