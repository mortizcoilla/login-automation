"""CLI: libera las pestañas de ficha acumuladas en Rayen (REQ-090).

Rayen permite 8 pestañas de ficha abiertas y el conteo es server-side:
nunca se limpia al re-loguear, se acumula entre corridas. Al llegar al
limite, toda apertura nueva se bloquea con el modal "Supero maximo de
pestañas abiertas" y paso 3 produce notas sin identificacion ni
historial (o sin nota).

Este comando: entra a Rayen, descarta el modal (si esta), intenta
cerrar las pestañas 'FC:' acumuladas y deja volcado HTML de evidencia
en logs/ para ajustar los selectores de cierre si el DOM real no usa
ningun candidato conocido.

Uso:
    python -m src.tools.cerrar_pestanas_rayen --user yadira

Exit code: 0 si al terminar no quedan pestañas de ficha visibles;
1 si quedan (o no se pudo determinar).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cierra las pestañas de ficha ('FC: ...') acumuladas en "
            "Rayen para liberar el limite de 8 (REQ-090)."
        )
    )
    parser.add_argument(
        "--user",
        type=str,
        default="yadira",
        help="Usuario de config/users.json o .env USERS_<ID>_* (default: yadira)",
    )
    parser.add_argument(
        "--pasadas",
        type=int,
        default=3,
        help="Maximo de pasadas de cierre (default: 3; corta antes si no cierra nada).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("cerrar_pestanas")

    from src.core.rutas import ADJUNTOS_DIR
    from src.credentials import load_credentials
    from src.rayen import pestanas
    from src.rayen.navegador import ensure_session_alive, run_login, safe_quit

    credentials = load_credentials(args.user)
    download_dir = Path(ADJUNTOS_DIR) / "_chrome_dl"
    download_dir.mkdir(parents=True, exist_ok=True)

    driver = None
    try:
        driver = run_login(
            credentials,
            logger,
            download_dir=str(download_dir.resolve()),
        )
        if not ensure_session_alive(driver, logger):
            logger.error("Sesion invalida tras login.")
            return 1

        n_inicial = pestanas.contar_pestanas_ficha(driver)
        logger.info(f"[pestanas] Pestañas de ficha al entrar: {n_inicial}")
        if pestanas.modal_pestanas_presente(driver):
            pestanas.descartar_modal_pestanas(driver, logger)
        pestanas.volcar_tablero_pestanas(driver, logger)

        total = 0
        for pasada in range(1, args.pasadas + 1):
            accionados = pestanas.cerrar_pestanas_ficha(driver, logger)
            total += accionados
            logger.info(
                f"[pestanas] Pasada {pasada}/{args.pasadas}: "
                f"controles accionados={accionados}"
            )
            if not accionados:
                break

        n_final = pestanas.contar_pestanas_ficha(driver)
        logger.warning(
            f"[pestanas] Resultado: {n_inicial} -> {n_final} pestañas visibles "
            f"(controles accionados: {total}). "
            "Si quedan pestañas, abrir el volcado HTML mas reciente en logs/ "
            "e identificar el control de cierre real para ajustar "
            "XPATH_CANDIDATOS_CIERRE en src/rayen/pestanas.py."
        )
        return 0 if n_final == 0 else 1
    finally:
        if driver is not None:
            try:
                safe_quit(driver, logger)
            except Exception:
                pass


if __name__ == "__main__":
    sys.exit(main())
