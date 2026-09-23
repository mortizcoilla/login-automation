"""Abre la ficha de UN paciente en Rayen.

Hace exactamente:
  1. Login en Rayen
  2. Navega hasta la pagina de Pacientes citados
  3. Selecciona la fecha indicada
  4. Busca al paciente por nombre completo
  5. Doble click sobre su nombre para abrir la ficha
  6. Se queda en la pantalla con la informacion del paciente

Ejemplo de uso (Monserrat):
    python -m src.tools.crear_notas_clinicas --paciente "Monserrat Sofia Delgado Ramirez" --fecha 05-08-2026

Reglas:
- Procesa UN SOLO paciente por ejecucion.
- Login con ventana visible para que el operador valide.
- No modifica nada fuera de este script.
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from selenium.webdriver.remote.webdriver import WebDriver

# Forzar UTF-8 en consola Windows
with contextlib.suppress(AttributeError, OSError):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from src.core.rutas import ROOT

sys.path.insert(0, str(ROOT))

from src.core.rutas import INFO_PACIENTE_DIR
from src.credentials import load_credentials
from src.notas.anamnesis import guardar_respaldo_anamnesis
from src.notas.info_paciente import guardar_info_paciente
from src.notas.modelos import PacienteObjetivo
from src.notas.nota_clinica import (
    _rellenar_bloque_en_nota,
    guardar_nota_clinica,
    validar_nota_clinica,
)
from src.rayen.extraccion.atencion_actual import (
    click_atencion_actual,
    extraer_anamnesis,
    extraer_motivo_consulta,
)
from src.rayen.extraccion.diagnosticos import (
    extraer_actividades,
    extraer_diagnosticos,
    extraer_profesionales,
)
from src.rayen.extraccion.estratificacion import (
    extraer_estratificacion_ecicep,
)
from src.rayen.extraccion.historial import (
    extraer_historial,
)
from src.rayen.extraccion.identificacion import _wait_visible, extraer_identificacion
from src.rayen.extraccion.plan import (
    _filtrar_receta_mas_reciente,
    _tipo_atencion_es_recetas,
    extraer_laboratorio,
    extraer_recetas,
)
from src.rayen.navegacion import (
    select_date,
    sort_by_estado,
    volver_a_pacientes_citados,
)
from src.rayen.navegador import ensure_session_alive, run_login, safe_quit
from src.rayen.tabla import (
    _buscar_paciente_en_tabla,
    _doble_click_en_paciente,
)
from src.tools.informe_tecnico import (
    PacienteInforme,
    WarningsCollector,
    generar_informe_tecnico,
)


def _informe_mes_actual_path() -> Path:
    """Wrapper local para mantener el contrato con el resto del modulo.

    La implementacion real vive en `src.analysis.informe_paths` (single
    source of truth, sesion 2026-09-09).
    """
    from src.analysis.informe_paths import informe_mes_actual_path

    return informe_mes_actual_path()


INFORME_DEFAULT = _informe_mes_actual_path()


# ---- Parser del informe de fichas abiertas ----


def parsear_informe(ruta: Path) -> list[PacienteObjetivo]:
    """Lee el informe y devuelve la lista de pacientes objetivo.

    Wrapper del parser unificado (src.informes.parser, Fase 4b). El mapeo
    de columnas vive ALLA (layouts 4/5/6/7/8 + REQ-043 + REQ-053).
    """
    from src.informes.parser import parsear_pacientes_objetivo

    return parsear_pacientes_objetivo(ruta)


# ---- Paso 4.1: filtrar por fecha, buscar nombre, doble click ----


# ---- REQ-017: limite de Rayen - solo 8 fichas por sesion (reset al llegar) ----
MAX_FICHAS_POR_SESION = 8

# Directorio que Chrome usa para bajar archivos (prefs de Chrome en
# run_login). El cache de descargas queda como subdirectorio _chrome_dl/
# (gitignored). Los adjuntos ya no se procesan (REQ-033), pero el
# download_dir sigue configurado para que Chrome nunca muestre dialogos.
from src.core.rutas import ADJUNTOS_DIR

ADJUNTOS_DOWNLOAD_DIR = ADJUNTOS_DIR / "_chrome_dl"


# ---- Paso 4.3: guardar nota clinica en archivo .txt ----


def _reintentar_extraccion_anamnesis(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
    click_ok: bool,
    identificacion: dict[str, str],
    historial: str,
    diagnosticos: list[str],
    actividades: list[str],
    profesionales: list[str],
    recetas: list[str],
    laboratorio: list[str],
    examenes: str,
    otros_items: dict[str, str],
    estratificacion: dict[str, Any] | None,
    motivo_consulta: str,
    pautas: list[str],
    notas_dir: Path,
    max_intentos: int = 3,
) -> Path | None:
    """Sesion 2026-09-16 14:50 (regla Yadira): si la extraccion de
    anamnesis falla, NO escribir marker. El script debe REINTENTAR
    la extraccion (re-click en 'Atencion actual' + re-extraer
    anamnesis) hasta N veces. Solo si agota todos los reintentos
    retorna None (Yadira re-corre cuando Rayen este estable).

    Args:
        click_ok: si el click en 'Atencion actual' fue exitoso
            originalmente. Si False, no se puede re-clickear; retorna
            None inmediatamente.
        max_intentos: numero maximo de reintentos (default 3).

    Returns:
        Path al .md escrito si algun reintento tuvo exito, o None si
        agoto todos los reintentos sin exito.
    """
    if not click_ok:
        logger.warning(
            f"[crear_notas] {paciente.nombre}: panel NO cargo "
            f"(click_ok=False). No se puede reintentar la extraccion "
            f"desde aqui. Yadira debera re-correr con Rayen estable."
        )
        return None

    for intento in range(1, max_intentos + 1):
        logger.info(
            f"[crear_notas] {paciente.nombre}: reintento "
            f"{intento}/{max_intentos} de extraccion de anamnesis "
            f"(re-click 'Atencion actual')..."
        )
        try:
            # Re-click en "Atencion actual" para forzar recargar el
            # panel de Evaluacion. Si ya esta clickeado, no-op.
            click_atencion_actual(driver, logger)
            # Re-extraer anamnesis con el panel ya (re)cargado.
            anamnesis_nueva = extraer_anamnesis(driver, logger)
            if anamnesis_nueva and anamnesis_nueva.strip():
                # Reintento exitoso. Escribir nota con la nueva
                # anamnesis.
                logger.info(
                    f"[crear_notas] {paciente.nombre}: reintento "
                    f"{intento} exitoso ({len(anamnesis_nueva)} chars)."
                )
                return guardar_nota_clinica(
                    paciente,
                    identificacion,
                    historial,
                    anamnesis_nueva,
                    diagnosticos,
                    actividades,
                    profesionales,
                    pautas,
                    examenes,
                    otros_items,
                    estratificacion,
                    motivo_consulta,
                    recetas,
                    laboratorio,
                    notas_dir,
                    panel_cargo=paciente.panel_cargo,
                )
        except Exception as re_err:
            logger.warning(
                f"[crear_notas] {paciente.nombre}: reintento "
                f"{intento} lanzo excepcion: {type(re_err).__name__}: "
                f"{re_err!r}"
            )

    logger.error(
        f"[crear_notas] {paciente.nombre}: extraccion fallo despues "
        f"de {max_intentos} reintentos. No se escribe archivo. "
        f"Yadira debera re-correr `crear_notas_clinicas` cuando "
        f"Rayen este estable."
    )
    return None


def re_extraer_bloque(
    driver: WebDriver,
    logger: logging.Logger,
    bloque: str,
    click_ok: bool,
    identificacion: dict[str, str] | None = None,
    historial: str | None = None,
    anamnesis: str | None = None,
    motivo_consulta: str | None = None,
    diagnosticos: list[str] | None = None,
    actividades: list[str] | None = None,
    profesionales: list[str] | None = None,
    recetas: list[str] | None = None,
    laboratorio: list[str] | None = None,
) -> str | list[str] | dict[str, str] | None:
    """Re-extrae especificamente el bloque faltante desde Rayen.

    Sesion 2026-09-16 14:14 (regla Yadira): si validar_nota_clinica
    detecta un bloque vacio, el pipeline llama a esta funcion con el
    `driver` que sigue en la ficha del paciente (estamos dentro del
    mismo loop, no hemos navegado a otra ficha).

    NOTA: el `driver` aqui deberia estar todavia en la ficha del
    paciente, pero NO se asume. Si `click_ok` fue False originalmente,
    no se puede extraer el bloque (no hay panel cargado). En ese caso
    retorna None.

    Returns:
        Contenido del bloque re-extraido, o None si no se pudo.
    """
    if not click_ok:
        # Sin click en "Atencion actual", no se puede extraer nada del panel.
        logger.warning(
            f"[crear_notas] re-extraer {bloque}: click_ok=False, no se "
            f"puede re-extraer (panel no cargo)."
        )
        return None

    if bloque == "Identificacion":
        return extraer_identificacion(driver, logger)
    if bloque == "Historial de atenciones (ultimos 6 meses)":
        return extraer_historial(driver, logger)
    if bloque == "Nota clinica de Yadira":
        # Anamnesis: si tenemos la original, intentar re-fetch.
        return extraer_anamnesis(driver, logger)
    if bloque == "Diagnosticos":
        return extraer_diagnosticos(driver, logger)
    if bloque == "Actividades":
        return extraer_actividades(driver, logger)
    if bloque == "Profesionales":
        return extraer_profesionales(driver, logger)
    if bloque == "Plan - Recetas":
        return extraer_recetas(driver, logger)
    if bloque == "Plan - Laboratorio":
        return extraer_laboratorio(driver, logger)

    logger.warning(f"[crear_notas] re-extraer: bloque desconocido '{bloque}'")
    return None


# REQ-030: timeout panel 60s; sin carga -> placeholders + panel_cargo=false.
def _buscar_en_cualquier_frame(driver, xpath: str):
    """Busca un elemento en el doc principal y en todos los iframes."""
    from selenium.common.exceptions import NoSuchElementException
    from selenium.webdriver.common.by import By

    driver.switch_to.default_content()
    try:
        return driver.find_element(By.XPATH, xpath)
    except Exception:
        pass
    for frame in driver.find_elements(By.XPATH, "//iframe"):
        try:
            driver.switch_to.frame(frame)
        except Exception:
            continue
        try:
            return driver.find_element(By.XPATH, xpath)
        except Exception:
            driver.switch_to.default_content()
    driver.switch_to.default_content()
    raise NoSuchElementException(f"no encontrado en ningun frame: {xpath}")


def _cerrar_tutorial_onboarding(driver, logger) -> None:
    """Cierra el tutorial onboarding de Rayen si esta presente.

    El overlay puede vivir en un iframe o shadow DOM: se busca en
    frames y con JS recursivo, hasta 7 clicks ('siguiente'/'terminar'
    /'listo'/'finalizar').
    """
    import time as _time


    xpath_tutorial = (
        "//*[contains(translate(normalize-space(text()),"
        "'SIGUIENTEETERMINARLISTOFINALIZAR','siguienteeterminarlistofinalizar'),"
        " 'siguiente') or contains(translate(normalize-space(text()),"
        " 'TERMINAR','terminar'), 'terminar') or contains("
        "translate(normalize-space(text()), 'LISTO','listo'), 'listo') "
        "or contains(translate(normalize-space(text()), "
        "'FINALIZAR','finalizar'), 'finalizar')]"
    )
    driver.switch_to.default_content()
    for paso in range(1, 8):
        btn = None
        for _ in range(5):
            try:
                btn = _buscar_en_cualquier_frame(driver, xpath_tutorial)
                break
            except Exception:
                _time.sleep(1)
        if btn is None:
            logger.info("[crear_notas] Tutorial onboarding ausente o ya cerrado.")
            driver.switch_to.default_content()
            return
        logger.info(f"[crear_notas] Cerrando tutorial onboarding (click {paso})...")
        try:
            btn.click()
        except Exception:
            driver.execute_script("arguments[0].click();", btn)
        _time.sleep(0.5)
    driver.switch_to.default_content()


def paso_4_1_abrir_ficha(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
) -> bool:
    """Paso 4.1: filtra por fecha, busca al paciente por nombre, doble click.

    Devuelve True si abrio la ficha, False si no encontro al paciente.
    """
    logger.info(
        f"[crear_notas] 4.1 Paciente: {paciente.nombre} "
        f"| fecha={paciente.fecha} | tipo={paciente.tipo_atencion}"
    )

    # 4.1.a: filtrar por fecha
    select_date(driver, logger, fecha_str=paciente.fecha)
    sort_by_estado(driver, logger)

    # 4.1.b: buscar al paciente por nombre completo
    resultado_busqueda = _buscar_paciente_en_tabla(driver, logger, paciente.nombre)
    if resultado_busqueda is None:
        logger.warning(
            f"[crear_notas] No se encontro a '{paciente.nombre}' en la tabla del {paciente.fecha}"
        )
        return False
    row, nombre_rayen = resultado_busqueda
    # Si hubo match parcial, guardar el nombre real de Rayen como
    # metadato para que Mortadelo pueda matchear despues.
    if nombre_rayen is not None:
        paciente.nombre_rayen = nombre_rayen

    # 4.1.c: doble click en la fila para abrir la ficha
    _doble_click_en_paciente(driver, logger, row, nombre_objetivo=paciente.nombre)

    # Esperar a que el panel del paciente se cargue. Senal inequivoca:
    # la tabla de identificacion del paciente tiene <th> en <tbody>
    # (par label:valor). La tabla de Pacientes citados tiene <th> solo
    # en <thead>, asi que el xpath con [.//tbody/th] filtra
    # especificamente la del paciente.
    #
    # Sesion 2026-09-09: timeout subido de 15s a 30s. Caso Ana Patricia
    # Vivanco Munoz: el panel tarda >15s en cargar y el script
    # seguia con extraccion sobre un panel vacio, generando una nota
    # con placeholders "(no se pudo extraer...)". Con 30s cubrimos el
    # percentil alto de paginas lentas de Rayen sin penalizar el caso
    # normal (las paginas rapidas cargan en <5s).
    panel_xpath = (
        "//table[.//tbody/th] | "
        "//li[@id='anamnesis'] | "
        "//div[contains(@class,'side-card')]//*[contains(@class,'rct-tree')] | "
        # ECICEP-g3 a veces no tiene tabla de identificacion visible
        # (la estratificacion carga primero). Esperar el card tambien.
        "//*[contains(@class, 'stratification-card')]"
    )
    # Sesion 2026-09-16: 30s -> 60s para ECICEP-g3.
    # IMPORTANTE: NO hacer retry del doble-click aqui. El primer click
    # ya nos llevo a la ficha del paciente. Si el panel no cargo,
    # un segundo click no ayuda (la fila ya esta stale y ademas
    # get_pacientes_del_dia espera 15s por div.rt-tr-group que ya
    # no existe -> TimeoutException). Mejor: 1 sola espera de 60s,
    # si falla -> placeholder, navegar manualmente al siguiente.
    panel_timeout = 60
    panel = _wait_visible(driver, panel_xpath, timeout=panel_timeout)

    if panel is None:
        # Caso real 22-09-2026 (Lylian, paciente 8/12, fallo en las 3
        # corridas): el doble click aterriza en la vista 'Historia
        # clinica' con un badge 'NN Atencion actual' en la cabecera.
        # Entrar ahi: click al badge, cerrar el tutorial onboarding si
        # aparece, y re-esperar el panel 30s mas.
        logger.info(
            "[crear_notas] Panel ausente; intentando click en el badge "
            "'Atencion actual'..."
        )
        try:
            from selenium.webdriver.common.by import By

            badge = driver.find_element(
                By.XPATH,
                "//*[contains(normalize-space(text()), 'Atención actual')]",
            )
            driver.execute_script("arguments[0].click();", badge)
            _cerrar_tutorial_onboarding(driver, logger)
            panel = _wait_visible(driver, panel_xpath, timeout=30)
        except Exception as e:  # el badge no estaba o fallo el click
            logger.warning(f"[crear_notas] Badge no encontrado: {e}")

    if panel is None:
        # Panel no cargo en 60s(+30s). NO re-clickamos. Marcamos el flag
        # y dejamos que la extraccion proceda (devuelve vacios). La nota
        # se guarda con placeholders + flag REVISION.
        logger.warning(
            f"[crear_notas] Panel no aparecio en {panel_timeout}s. "
            f"Extraccion procedera sobre lo que haya; "
            f"guardar_nota_clinica() escribira placeholder con flag REVISION."
        )
        # Evidencia para diagnostico: que habia en pantalla.
        try:
            from src.core.rutas import SCREENSHOTS_DIR

            SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
            nombre_safe = paciente.nombre.replace(" ", "_")
            ruta = SCREENSHOTS_DIR / f"panel_timeout_{nombre_safe}.png"
            driver.save_screenshot(str(ruta))
            logger.warning(f"[crear_notas] Screenshot del timeout: {ruta.name}")
        except Exception:
            pass
        paciente.panel_cargo = False
    else:
        logger.info(f"[crear_notas] Panel del paciente cargado ({panel.tag_name})")

    logger.info(
        f"[crear_notas] Ficha abierta para {paciente.nombre} (URL actual: {driver.current_url})"
    )
    return True


# ---- Iterador principal (paso 4.6: sigue con el siguiente) ----


def iterar_pacientes(
    driver: WebDriver,
    logger: logging.Logger,
    pacientes: list[PacienteObjetivo],
) -> dict[str, int]:
    """Por cada paciente: ejecutar paso 4.1. Si falla, sigue con el siguiente."""
    stats = {"procesados": 0, "abiertos": 0, "no_encontrados": 0, "errores": 0}
    for i, p in enumerate(pacientes, 1):
        logger.info(f"[crear_notas] ({i}/{len(pacientes)}) Procesando: {p.nombre} ({p.fecha})")
        try:
            stats["procesados"] += 1
            ok = paso_4_1_abrir_ficha(driver, logger, p)
            if ok:
                stats["abiertos"] += 1
            else:
                stats["no_encontrados"] += 1
        except Exception as e:
            stats["errores"] += 1
            logger.error(f"[crear_notas] Error con {p.nombre}: {e}. Sigue con el siguiente.")
            continue
    return stats


# ---- Main ----


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Crear notas clinicas desde Rayen. "
            "Por defecto procesa UN paciente (--paciente + --fecha). "
            "Con --todos procesa los pacientes del informe del mes en curso."
        )
    )
    parser.add_argument(
        "--paciente",
        type=str,
        default=None,
        help="Nombre completo del paciente a procesar (modo 1 paciente).",
    )
    parser.add_argument(
        "--fecha",
        type=str,
        default=None,
        help="Fecha del paciente en formato dd-mm-yyyy (modo 1 paciente).",
    )
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Procesa los pacientes del informe del mes en curso (modo batch).",
    )
    parser.add_argument(
        "--informe",
        type=Path,
        default=None,
        help=(
            "Path al informe MENSUAL de fichas abiertas "
            f"(default: {_informe_mes_actual_path().name}). "
            "NO usar el informe anual (_completo.txt) — esta prohibido."
        ),
    )
    parser.add_argument(
        "--user",
        type=str,
        default="yadira",
        help="Usuario de config/users.json o .env USERS_<ID>_* (default: yadira)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    # Default de --informe: el informe del mes en curso.
    if args.informe is None:
        args.informe = _informe_mes_actual_path()

    # Guard: el informe anual (_completo) NO se puede usar con --todos.
    # Es una operacion distinta, para otros propositos, y no debe
    # mezclarse con el batch mensual. Si llega por error, abortar claro.
    if args.todos and "_completo" in args.informe.name:
        parser.error(
            f"REFUSADO: {args.informe.name} es el informe ANUAL, "
            f"no se puede usar con --todos. "
            f"Usa el informe del mes en curso ({_informe_mes_actual_path().name}) "
            f"o pasa --informe con un path mensual explicito."
        )

    # Validar modo
    if not args.todos and (not args.paciente or not args.fecha):
        parser.error("Modo 1 paciente requiere --paciente y --fecha. O usa --todos.")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("crear_notas_clinicas")

    # 1. Cargar credenciales
    try:
        credentials = load_credentials(args.user)
    except (KeyError, ValueError) as e:
        logger.error(f"Error cargando credenciales: {e}")
        return 2
    logger.info(f"[crear_notas] Credenciales cargadas para usuario: {args.user}")

    # 2. Construir la lista de pacientes
    if args.todos:
        pacientes = parsear_informe(args.informe)
        logger.info(
            f"[crear_notas] Modo --todos: {len(pacientes)} pacientes del informe {args.informe.name}"
        )
    else:
        pacientes = [
            PacienteObjetivo(
                fecha=args.fecha,
                nombre=args.paciente,
                tipo_atencion="(no se valida contra informe)",
                razon="",
            )
        ]
        logger.info(f"[crear_notas] Modo 1 paciente: {pacientes[0].nombre} | {pacientes[0].fecha}")

    # 3. Pasos 1-3: login + box + Pacientes citados (via run_login)
    driver: WebDriver | None = None
    stats = {"procesados": 0, "abiertos": 0, "guardados": 0, "saltados": 0, "errores": 0}
    fichas_en_sesion = 0
    # Carpeta donde Chrome dejara los adjuntos descargados. Se crea
    # aca para que exista cuando _build_chrome_options la reciba.
    ADJUNTOS_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Capturador de warnings para el informe tecnico (separado de la ficha).
    warnings_collector = WarningsCollector()
    warnings_collector.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logging.getLogger("crear_notas").addHandler(warnings_collector)
    # Lista de informes por paciente.
    pacientes_informe: list[PacienteInforme] = []
    import time as _time

    logger.info(f"[crear_notas] Download dir Chrome: {ADJUNTOS_DOWNLOAD_DIR.resolve()}")
    try:
        driver = run_login(
            credentials,
            logger,
            download_dir=str(ADJUNTOS_DOWNLOAD_DIR.resolve()),
        )
        if not ensure_session_alive(driver, logger):
            logger.error("Sesion invalida tras login.")
            return 1
        logger.info("[crear_notas] Login + navegacion OK.")

        # 4. Por cada paciente: 4.1 (abrir ficha) + 4.2 (extraer) + 4.3 (guardar)
        notas_dir = ROOT / "data" / "notas_clinicas"
        for i, paciente in enumerate(pacientes, 1):
            t_inicio = _time.time()
            warnings_collector.reset()  # snapshot limpio por paciente
            logger.info(
                f"[crear_notas] ({i}/{len(pacientes)}) "
                f"Procesando: {paciente.nombre} ({paciente.fecha})"
            )
            stats["procesados"] += 1
            ficha_ok = False
            pinfo = PacienteInforme(
                nombre=paciente.nombre,
                fecha=paciente.fecha,
            )
            try:
                # Paso 4.1
                ok = paso_4_1_abrir_ficha(driver, logger, paciente)
                if not ok:
                    logger.warning(
                        f"[crear_notas] No se encontro a {paciente.nombre} en la tabla. Saltando."
                    )
                    stats["saltados"] += 1
                    pinfo.estado = "skipped"
                    pinfo.match_tipo = "ninguno"
                    pinfo.warnings = warnings_collector.snapshot()
                    pacientes_informe.append(pinfo)
                    continue
                stats["abiertos"] += 1
                ficha_ok = True
                # Si hubo match parcial, paso_4_1 setea paciente.nombre_rayen.
                if paciente.nombre_rayen:
                    pinfo.match_tipo = "parcial"
                    pinfo.match_nombre_rayen = paciente.nombre_rayen
                else:
                    pinfo.match_tipo = "exacto"

                # Paso 4.2
                # REQ-024: estratificacion ECICEP PRIMERO (su modal debe cerrarse antes).
                # Razon: la estratificacion abre un modal; hay que cerrarlo
                # con el boton "Salir" antes de cualquier otra extraccion, para
                # que el overlay/modal no intercepte clicks posteriores.
                # 1) Estratificacion (incluye apertura popover+modal, parseo
                #    y cierre via boton "Salir" + cierre de popover).
                # 2) Identificacion, 3) Historial.
                # 4) Click en Atencion actual.
                # 5) Motivo, 6) Anamnesis, 7) Diagnostico, 8) Actividad,
                #    9) Profesionales, 10) Plan -> Recetas, 11) Plan -> Laboratorio.
                # Fuera de scope: examenes adjuntos, pautas, otros items,
                # plan -> imagenologia, plan -> interconsulta.
                estratificacion = extraer_estratificacion_ecicep(driver, logger)
                identificacion = extraer_identificacion(driver, logger)
                # Historial ANTES del click en "Atencion actual" porque ese
                # click puede colapsar el panel del historial.
                historial = extraer_historial(driver, logger)
                # REQ-033: fuera de scope: examenes, pautas, otros items, imagenologia, interconsulta.
                # Secciones fuera de scope (no se extraen, se pasan vacias):
                examenes = ""
                # Ahora si hacemos click en Atencion actual
                click_ok = click_atencion_actual(driver, logger)
                motivo_consulta = extraer_motivo_consulta(driver, logger) if click_ok else ""
                anamnesis = extraer_anamnesis(driver, logger) if click_ok else ""
                # Paso 4.2.5 (sesion 2026-09-16 15:14): respaldo de la
                # anamnesis cruda de Yadira en anamnesis/<paciente>_<fecha>.md.
                # Es un .md liviano, separado de la nota clinica completa,
                # para que Yadira tenga una copia de seguridad local facil
                # de buscar por nombre y fecha. Solo si la anamnesis no
                # esta vacia. Sesion 15:27: tambien incluye motivo de
                # atencion como blockquote antes de la anamnesis (es la
                # primera linea que Yadira escribe en Rayen).
                if anamnesis:
                    guardar_respaldo_anamnesis(paciente, anamnesis, motivo_consulta=motivo_consulta)
                diagnosticos = extraer_diagnosticos(driver, logger) if click_ok else []
                actividades = extraer_actividades(driver, logger) if click_ok else []
                profesionales = extraer_profesionales(driver, logger) if click_ok else []
                # Plan (panel derecho). Recetas y Laboratorio se extraen
                # del mismo panel #right-side-attention que ya esta visible
                # tras click_atencion_actual. Si click_ok fallo, no se
                # intenta (no hay panel que leer).
                recetas = extraer_recetas(driver, logger) if click_ok else []
                # Regla Yadira 2026-08-26: si el tipo de atencion es
                # "Recetas", dejamos SOLO la prescripcion con la Vigencia
                # mas reciente en el bloque PLAN RECETAS del .txt. Para
                # cualquier otro tipo, se conservan todas las recetas.
                if _tipo_atencion_es_recetas(paciente.tipo_atencion) and len(recetas) > 1:
                    recetas_filtradas = _filtrar_receta_mas_reciente(recetas)
                    logger.info(
                        f"[crear_notas] tipo=Recetas: filtradas "
                        f"{len(recetas)} -> {len(recetas_filtradas)} "
                        f"prescripcion(es) (mas reciente)"
                    )
                    recetas = recetas_filtradas
                laboratorio = extraer_laboratorio(driver, logger) if click_ok else []
                # Fuera de scope:
                pautas: list[str] = []
                otros_items: dict[str, Any] = {}

                pinfo.extraccion = {
                    "identificacion_campos": len(identificacion),
                    "historial_caracteres": len(historial or ""),
                    "anamnesis_caracteres": len(anamnesis or ""),
                    "motivo_consulta_caracteres": len(motivo_consulta or ""),
                    "diagnosticos": len(diagnosticos or []),
                    "actividades": len(actividades or []),
                    "profesionales": len(profesionales or []),
                    "pautas": len(pautas or []),
                    "examenes_adjuntos_chars": len(examenes or ""),
                    "recetas_prescripciones": len(recetas or []),
                    "laboratorio_ordenes": len(laboratorio or []),
                    "estratificacion_grupo": ((estratificacion or {}).get("grupo")),
                    "estratificacion_cronicos": len((estratificacion or {}).get("cronicos") or []),
                    "estratificacion_agudos": len((estratificacion or {}).get("agudos") or []),
                }

                # Paso 4.3
                try:
                    out_path = guardar_nota_clinica(
                        paciente,
                        identificacion,
                        historial,
                        anamnesis,
                        diagnosticos,
                        actividades,
                        profesionales,
                        pautas,
                        examenes,
                        otros_items,
                        estratificacion,
                        motivo_consulta,
                        recetas,
                        laboratorio,
                        notas_dir,
                        panel_cargo=paciente.panel_cargo,
                    )

                    if out_path is None:
                        raise RuntimeError(
                            f"guardar_nota_clinica no escribio la nota de {paciente.nombre}"
                        )
                    # Paso 4.5 (sesion 2026-09-16 17:45): documento
                    # complementario en data/info_paciente/ con TODA la
                    # info del paciente MENOS la anamnesis cruda. Yadira
                    # lo usa para "mirar al paciente de un vistazo" sin
                    # leer el texto libre de la consulta. La anamnesis
                    # sigue en data/anamnesis/ (respaldo separado).
                    guardar_info_paciente(
                        paciente,
                        identificacion,
                        historial,
                        diagnosticos,
                        actividades,
                        profesionales,
                        recetas,
                        laboratorio,
                        estratificacion,
                        info_paciente_dir=INFO_PACIENTE_DIR,
                        panel_cargo=paciente.panel_cargo,
                    )
                    # Paso 4.4: VALIDACION POST-WRITE + RE-FETCH DE HUECOS.
                    # Regla Yadira 2026-09-16 14:14: despues de escribir,
                    # el script verifica que todos los bloques tengan
                    # contenido. Si falta alguno, va a buscarlo a Rayen
                    # con el `driver` que sigue activo y sobrescribe el
                    # archivo.
                    faltantes = validar_nota_clinica(out_path)
                    if faltantes:
                        logger.warning(
                            f"[crear_notas] {paciente.nombre}: "
                            f"validacion post-write encontro {len(faltantes)} "
                            f"bloque(s) sin contenido: {faltantes}. "
                            f"Re-fetch + re-write."
                        )
                        bloques_reescritos: list[str] = []
                        bloques_aun_vacios: list[str] = []
                        for bloque in faltantes:
                            nuevo = re_extraer_bloque(
                                driver,
                                logger,
                                bloque,
                                click_ok,
                                identificacion=identificacion,
                                historial=historial,
                                anamnesis=anamnesis,
                                motivo_consulta=motivo_consulta,
                                diagnosticos=diagnosticos,
                                actividades=actividades,
                                profesionales=profesionales,
                                recetas=recetas,
                                laboratorio=laboratorio,
                            )
                            if nuevo:
                                _rellenar_bloque_en_nota(out_path, bloque, nuevo)
                                bloques_reescritos.append(bloque)
                            else:
                                bloques_aun_vacios.append(bloque)
                        if bloques_reescritos:
                            logger.info(
                                f"[crear_notas] {paciente.nombre}: "
                                f"re-fetch completo para {bloques_reescritos}."
                            )
                        if bloques_aun_vacios:
                            logger.warning(
                                f"[crear_notas] {paciente.nombre}: "
                                f"no se pudo re-extraer: {bloques_aun_vacios}. "
                                f"Yadira debera revisar manualmente."
                            )

                    stats["guardados"] += 1
                    pinfo.estado = "ok"
                    logger.info(f"[crear_notas] {paciente.nombre} OK -> {out_path.name}")
                except ValueError as ve:
                    # Regla Yadira 2026-09-16 14:50 (correccion): NO
                    # escribir markers. Si la extraccion fallo, el
                    # script debe REINTENTAR (re-click en 'Atencion
                    # actual' + re-extraer anamnesis) hasta N veces.
                    # Solo si agota todos los reintentos, skip
                    # silencioso (Yadira re-corre cuando Rayen este
                    # estable).
                    stats["errores_extraccion"] = stats.get("errores_extraccion", 0) + 1
                    pinfo.errores.append(f"ValueError: {ve!r}")
                    out_reintento = _reintentar_extraccion_anamnesis(
                        driver,
                        logger,
                        paciente,
                        click_ok,
                        identificacion,
                        historial,
                        diagnosticos,
                        actividades,
                        profesionales,
                        recetas,
                        laboratorio,
                        examenes,
                        otros_items,
                        estratificacion,
                        motivo_consulta,
                        pautas,
                        notas_dir,
                    )
                    if out_reintento is not None:
                        stats["guardados"] += 1
                        pinfo.estado = "ok"
                        logger.info(
                            f"[crear_notas] {paciente.nombre} OK "
                            f"(tras reintento) -> {out_reintento.name}"
                        )
                    else:
                        pinfo.estado = "extraccion_fallida"
                        logger.error(
                            f"[crear_notas] {paciente.nombre}: "
                            f"extraccion fallo tras agotar reintentos. "
                            f"Yadira re-corre cuando Rayen este estable."
                        )

            except Exception as e:
                stats["errores"] += 1
                pinfo.estado = "error"
                # Guardar tipo de excepcion + mensaje. Mensajes vacios ("Message: \n")
                # son tipicos de WebDriverException con msg vacio; el TIPO es lo
                # unico que da pista del problema real.
                import traceback as _tb

                err_repr = f"{type(e).__name__}: {e!r}"
                pinfo.errores.append(err_repr)
                tb_short = _tb.format_exc().splitlines()[-3:]
                logger.error(
                    f"[crear_notas] Error con {paciente.nombre}: {err_repr}. "
                    f"Ultimas lineas del traceback: {tb_short}. "
                    f"Sigue con el siguiente."
                )

            pinfo.warnings = warnings_collector.snapshot()
            pinfo.tiempo_segundos = round(_time.time() - t_inicio, 2)
            pacientes_informe.append(pinfo)

            # Despues de CADA paciente (exitoso o no), volver a la lista
            # para el siguiente. Y si llegamos al limite, resetear sesion.
            if ficha_ok:
                fichas_en_sesion += 1
            quedan = len(pacientes) - i
            necesita_reset = fichas_en_sesion >= MAX_FICHAS_POR_SESION and quedan > 0
            if necesita_reset:
                logger.warning(
                    f"[crear_notas] Limite de {MAX_FICHAS_POR_SESION} fichas alcanzado. "
                    f"Reseteando sesion de Rayen..."
                )
                safe_quit(driver, logger)
                driver = None
                driver = run_login(
                    credentials,
                    logger,
                    download_dir=str(ADJUNTOS_DOWNLOAD_DIR.resolve()),
                )
                if not ensure_session_alive(driver, logger):
                    logger.error("Sesion invalida tras re-login.")
                    return 1
                fichas_en_sesion = 0
            elif quedan > 0:
                # Volver a la lista de Pacientes citados para el siguiente
                volver_a_pacientes_citados(driver, logger)

        logger.info(
            f"[crear_notas] === Resumen final === "
            f"procesados={stats['procesados']}, "
            f"abiertos={stats['abiertos']}, "
            f"guardados={stats['guardados']}, "
            f"saltados={stats['saltados']}, "
            f"errores={stats['errores']}"
        )

        # REQ-032: verificacion de target del batch contra el informe.
        # Verificacion de target: el informe dice N fichas abiertas, el
        # script tiene que procesar las N. Si falta alguna, alertar.
        if args.todos:
            total_objetivo = len(pacientes)
            total_ok = stats["abiertos"]
            faltantes_target = total_objetivo - total_ok
            if faltantes_target > 0:
                logger.warning(
                    f"[crear_notas] === TARGET NO CUMPLIDO === "
                    f"Objetivo informe: {total_objetivo} fichas, "
                    f"abiertas OK: {total_ok}, "
                    f"FALTAN: {faltantes_target}. "
                    f"Revisar logs de 'No se encontro a ...' arriba."
                )
            else:
                logger.info(
                    f"[crear_notas] === TARGET OK === "
                    f"Las {total_objetivo} fichas del informe "
                    f"fueron procesadas."
                )

            # 5. Generar informe tecnico (JSON para Miguel).
            # Contiene warnings, errores, tiempos, datos extraidos por
            # paciente. NO va a la ficha, va a un archivo separado.
            informe = generar_informe_tecnico(
                modo="todos",
                informe=str(args.informe.name),
                pacientes=pacientes_informe,
                stats=stats,
            )
            informes_dir = ROOT / "data" / "analysis"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            informe_path = informes_dir / f"informe_tecnico_{ts}.json"
            informe.guardar(informe_path)
            logger.info(f"[crear_notas] Informe tecnico guardado en: {informe_path}")

        # 6. Cerrar navegador automaticamente al terminar
        logger.info("[crear_notas] Cerrando navegador...")
        return 0
    except Exception as e:
        logger.error(f"[crear_notas] Error fatal: {e}")
        return 1
    finally:
        if driver is not None:
            safe_quit(driver, logger)


if __name__ == "__main__":
    sys.exit(main())
