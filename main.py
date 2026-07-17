import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.logger_config import setup_logger
from src.credentials import load_credentials, prompt_user_id
from src.browser_automation import (
    run_login,
    select_date,
    sort_by_estado,
    get_pacientes_iniciados,
    extraer_datos_fila,
)
from src.plantillas import (
    sanitizar_tipo,
    cargar_plantilla,
    rellenar_plantilla,
    guardar_plantilla,
)


def mostrar_resumen(iniciados, user_id, fecha_consulta):
    print()
    print("=" * 70)
    print(f"  Hola {user_id} — Fecha: {fecha_consulta}")
    print(f"  Tienes {len(iniciados)} fichas abiertas")
    print(f"  Aqui tienes un resumen:")
    print("-" * 70)
    for i, row in enumerate(iniciados, 1):
        d = extraer_datos_fila(row)
        tipo = sanitizar_tipo(d["tipo_atencion"])
        print(f"  {i:2d}. {d['nombre']:<35s} | {tipo:<30s} | {d['razon']}")
    print("-" * 70)


def loop_pacientes(iniciados, logger):
    while True:
        try:
            opcion = input(
                f"\nSeleccione paciente (1-{len(iniciados)}, 0 para salir): "
            ).strip()
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
            print(f"Paciente '{datos['nombre']}' te visita por "
                  f"'{datos['razon']}' para '{tipo}'")

            plantilla = cargar_plantilla(datos["tipo_atencion"])
            if plantilla is None:
                print(f"  [AVISO] No existe plantilla para '{tipo}'")
                print(f"  Creala en: plantillas/{tipo}.txt")
                continue

            if not plantilla.strip():
                print(f"  [AVISO] Plantilla para '{tipo}' esta vacia")
                print(f"  Editala en: plantillas/{tipo}.txt")
                continue

            rellena = rellenar_plantilla(plantilla, datos)
            print()
            print("--- PLANTILLA RELLENA ---")
            print(rellena)
            print("--------------------------")

            resp = input("¿Aprobar? (s/N): ").strip().lower()
            if resp == "s":
                ruta = guardar_plantilla(rellena, datos["nombre"])
                print(f"  Guardado en: {ruta}")
                logger.info(f"Plantilla guardada para {datos['nombre']}")
            else:
                print("  Plantilla omitida.")

        except ValueError:
            print("Ingrese un numero valido.")


def main():
    logger = setup_logger()
    logger.info("=" * 50)
    logger.info("Aplicacion de automatizacion de login iniciada")
    logger.info("=" * 50)

    driver = None
    try:
        user_id = prompt_user_id()
        logger.info(f"Usuario seleccionado: {user_id}")

        credentials = load_credentials(user_id)
        logger.info(f"Credenciales cargadas para usuario: {user_id}")

        driver = run_login(credentials, logger)
        fecha_consulta = select_date(driver, logger)

        sort_by_estado(driver, logger)
        iniciados = get_pacientes_iniciados(driver, logger)

        mostrar_resumen(iniciados, user_id, fecha_consulta)
        loop_pacientes(iniciados, logger)

        logger.info("Presione Enter para cerrar el navegador...")
        input()

    except FileNotFoundError as e:
        logger.error(f"Error de archivo: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Error de datos: {e}")
        sys.exit(1)
    except KeyError as e:
        logger.error(f"Error de usuario: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error critico durante la automatizacion: {e}")
        sys.exit(1)
    finally:
        if driver:
            driver.quit()
            logger.info("Navegador cerrado")


if __name__ == "__main__":
    main()
