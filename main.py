from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

from src.browser_automation import (
    ensure_session_alive,
    extraer_datos_fila,
    get_pacientes_iniciados,
    run_login,
    safe_quit,
    select_date,
    sort_by_estado,
)
from src.constants import SEPARADOR_ANCHO
from src.credentials import list_known_users, load_credentials, prompt_user_id
from src.logger_config import setup_logger
from src.plantillas import (
    cargar_plantilla,
    guardar_plantilla,
    rellenar_plantilla,
    sanitizar_tipo,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="login-automation",
        description="Automatizacion de login y plantillas para Rayen APS",
    )
    parser.add_argument("--user", "-u", help="Identificador de usuario (omite el prompt)")
    parser.add_argument("--date", "-d", help="Fecha objetivo dd-mm-yyyy (omite el prompt)")
    parser.add_argument("--headless", action="store_true", help="Ejecutar Chrome en headless")
    parser.add_argument(
        "--no-input",
        action="store_true",
        help="Modo no interactivo (falla si faltan --user o --date)",
    )
    parser.add_argument(
        "--list-users",
        action="store_true",
        help="Lista usuarios conocidos (env + json) y sale",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Nivel de log (default: INFO o $LOG_LEVEL)",
    )
    return parser.parse_args(argv)


def mostrar_resumen(
    iniciados: list[Any],
    user_id: str,
    fecha_consulta: str,
) -> None:
    print()
    print("=" * SEPARADOR_ANCHO)
    print(f"  Hola {user_id} - Fecha: {fecha_consulta}")
    print(f"  Tienes {len(iniciados)} fichas abiertas")
    print("-" * SEPARADOR_ANCHO)
    for i, row in enumerate(iniciados, 1):
        d = extraer_datos_fila(row)
        tipo = sanitizar_tipo(d["tipo_atencion"])
        print(f"  {i:2d}. {d['nombre']:<35s} | {tipo:<30s} | {d['razon']}")
    print("-" * SEPARADOR_ANCHO)


def loop_pacientes(iniciados: list[Any], logger: logging.Logger) -> dict[str, int]:
    stats = {"procesados": 0, "aprobados": 0, "omitidos": 0, "sin_plantilla": 0}

    while True:
        try:
            opcion = input(f"\nSeleccione paciente (1-{len(iniciados)}, 0 para salir): ").strip()
            if opcion == "0":
                logger.info("Sesion finalizada por el usuario.")
                break

            idx = int(opcion) - 1
            if not (0 <= idx < len(iniciados)):
                print(f"Numero invalido. Elija entre 1 y {len(iniciados)}")
                continue

            row = iniciados[idx]
            datos = extraer_datos_fila(row)
            tipo = sanitizar_tipo(datos["tipo_atencion"])

            print()
            print(f"Paciente '{datos['nombre']}' te visita por '{datos['razon']}' para '{tipo}'")

            plantilla = cargar_plantilla(datos["tipo_atencion"])
            if plantilla is None:
                stats["sin_plantilla"] += 1
                print(f"  [AVISO] No existe plantilla para '{tipo}'")
                print(f"  Creala en: plantillas/{tipo}.txt")
                continue
            if not plantilla.strip():
                stats["sin_plantilla"] += 1
                print(f"  [AVISO] Plantilla para '{tipo}' esta vacia")
                print(f"  Editala en: plantillas/{tipo}.txt")
                continue

            rellena = rellenar_plantilla(plantilla, datos)
            print()
            print("--- PLANTILLA RELLENA ---")
            print(rellena)
            print("-------------------------")

            resp = input("Aprobar? (s/N): ").strip().lower()
            stats["procesados"] += 1
            if resp == "s":
                ruta = guardar_plantilla(rellena, datos["nombre"])
                print(f"  Guardado en: {ruta}")
                logger.info(f"Plantilla guardada para {datos['nombre']}")
                stats["aprobados"] += 1
            else:
                print("  Plantilla omitida.")
                stats["omitidos"] += 1

        except ValueError:
            print("Ingrese un numero valido.")
        except (EOFError, KeyboardInterrupt):
            print("\nEntrada interrumpida. Volviendo al menu.")
            continue

    return stats


def run(args: argparse.Namespace) -> int:
    logger = setup_logger(level=args.log_level)
    logger.info("=" * 50)
    logger.info("Aplicacion de automatizacion de login iniciada")
    logger.info("=" * 50)

    if args.list_users:
        users = list_known_users()
        print("Usuarios disponibles:")
        for u in users:
            print(f"  - {u}")
        return 0

    if args.no_input and not args.user:
        logger.error("--no-input requiere --user")
        return 2

    user_id = args.user or prompt_user_id()
    logger.info(f"Usuario seleccionado: {user_id}")

    credentials = load_credentials(user_id)
    logger.info(f"Credenciales cargadas para usuario: {user_id}")

    driver = None
    try:
        driver = run_login(credentials, logger, headless=args.headless)
        if not ensure_session_alive(driver, logger):
            logger.error("Sesion invalida tras login.")
            return 1

        fecha_consulta = select_date(driver, logger, fecha_str=args.date if args.no_input else None)

        sort_by_estado(driver, logger)
        iniciados = get_pacientes_iniciados(driver, logger)

        if not iniciados:
            print("\nNo hay fichas en estado 'Iniciado' para esta fecha.")
            return 0

        mostrar_resumen(iniciados, user_id, fecha_consulta)

        if args.no_input:
            logger.info("Modo no interactivo: saliendo sin procesar pacientes.")
            return 0

        stats = loop_pacientes(iniciados, logger)
        logger.info(
            f"Resumen final -> procesados: {stats['procesados']}, "
            f"aprobados: {stats['aprobados']}, omitidos: {stats['omitidos']}, "
            f"sin plantilla: {stats['sin_plantilla']}"
        )

        if not args.no_input:
            from contextlib import suppress

            with suppress(EOFError):
                input("\nPresione Enter para cerrar el navegador...")
        return 0

    except FileNotFoundError as e:
        logger.error(f"Error de archivo: {e}")
        return 1
    except ValueError as e:
        logger.error(f"Error de datos: {e}")
        return 1
    except KeyError as e:
        logger.error(f"Error de usuario: {e}")
        return 1
    except Exception as e:
        logger.exception(f"Error critico durante la automatizacion: {e}")
        return 1
    finally:
        safe_quit(driver, logger)


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except KeyboardInterrupt:
        print("\nInterrumpido por el usuario.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
