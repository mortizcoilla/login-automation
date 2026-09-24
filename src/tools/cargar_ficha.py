"""Paso 8 / cargar_ficha: pega la ficha generada (paso 7) en Rayen.

Origen del texto: `data/fichas_generadas/ficha_<pac>_<fecha>.md`
(fuente unica de verdad: paso 7 / Mortadelo).

Flujo por paciente:
  1. Lee el archivo del paso 7. Si no existe: skip + log.
  2. Login en Rayen (ventana visible para que Yadira valide).
  3. Navega a Pacientes citados y filtra por la fecha del paciente.
  4. Doble click sobre el nombre -> abre la ficha del paciente.
     (Flujo compartido con paso 3 via `src.rayen.flujos.apertura_ficha`.)
  5. Detecta el editor interno de Rayen y pega el contenido del .md.
  6. NO auto-envia: Yadira revisa y aprieta Guardar ella misma.
  7. Registra el resultado en `data/trazabilidad_carga/carga_<ts>.json`.

Modos:
  --paciente "Nombre Apellido" --fecha dd-mm-yyyy   (1 paciente)
  --todos                                          (batch del informe
                                                     del mes en curso)

Pendiente: el selector concreto del campo "Anamnesis" / "Atencion"
dentro de Rayen. Mientras tanto, el pegado loguea NotImplementedError
y la corrida queda registrada como 'skip: pendiente selector'.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

with contextlib.suppress(AttributeError, OSError):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from src.core.nombres import safe_filename
from src.core.rutas import (
    ANAMNESIS_DIR,
    FICHAS_GENERADAS_DIR,
    TRAZABILIDAD_CARGA_DIR,
)
from src.credentials import load_credentials
from src.notas.modelos import PacienteObjetivo
from src.rayen.escritura.editor_anamnesis import (
    ResultadoPegado,
    TipoEditor,
    abrir_editor_anamnesis,
    guardar_editor_anamnesis,
    pegar_en_editor,
)
from src.rayen.flujos.apertura_ficha import abrir_ficha_por_nombre
from src.rayen.navegacion import volver_a_pacientes_citados
from src.rayen.navegador import run_login, safe_quit


# ---- Helpers de testing (re-exportados para que los tests los importen
# directamente desde `src.tools.cargar_ficha`). NO se usan en produccion.
def pegador_fake_ok(caracteres: int) -> ResultadoPegado:
    """Devuelve un ResultadoPegado exitoso para tests."""
    return ResultadoPegado(
        ok=True,
        tipo_editor=TipoEditor.TEXTAREA,
        caracteres_pegados=caracteres,
    )


def pegador_fake_pendiente_selector() -> ResultadoPegado:
    """Devuelve un ResultadoPegado con motivo 'pendiente selector'."""
    return ResultadoPegado(
        ok=False,
        tipo_editor=TipoEditor.TEXTAREA,
        motivo="pegar_en_textarea: pendiente selector",
        caracteres_pegados=0,
    )


def _informe_mes_actual_path() -> Path:
    """Wrapper local para mantener el contrato con el resto del modulo."""
    from src.analysis.informe_paths import informe_mes_actual_path

    return informe_mes_actual_path()


# ---- Parser del informe de fichas abiertas ----


def parsear_informe(ruta: Path) -> list[PacienteObjetivo]:
    """Lee el informe mensual y devuelve los pacientes objetivo."""
    from src.informes.parser import parsear_pacientes_objetivo

    return parsear_pacientes_objetivo(ruta)


# ---- Resultado por paciente ----


@dataclass
class ResultadoCarga:
    """Registro de un intento de carga. Se acumula en la trazabilidad."""

    nombre: str
    fecha: str
    ficha_path: str = ""
    estado: str = "pendiente"  # ok / skip / error / pendiente_selector
    abierta: bool = False  # la ficha se abrio en Rayen (hubo doble click)
    motivo: str = ""
    tipo_editor: str = ""
    caracteres_pegados: int = 0
    timestamp: str = ""


# ---- Loader del archivo del paso 7 ----


def _normalizar_contenido(texto: str) -> str:
    """Colapsa espacios y saltos: comparacion tolerante de contenidos."""
    return re.sub(r"\s+", " ", texto).strip()


def _path_ficha_generada(nombre: str, fecha: str, fichas_dir: Path) -> Path:
    """Construye el path al .md de paso 7 para el (nombre, fecha)."""
    safe = safe_filename(nombre)
    return fichas_dir / f"ficha_{safe}_{fecha}.md"


def leer_ficha_generada(nombre: str, fecha: str, fichas_dir: Path) -> str | None:
    """Lee el .md de paso 7. None si no existe o esta vacio."""
    path = _path_ficha_generada(nombre, fecha, fichas_dir)
    if not path.exists():
        return None
    texto = path.read_text(encoding="utf-8", errors="replace").strip()
    return texto or None


# ---- Carga de un paciente ----


def cargar_ficha_de_paciente(
    driver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
    fichas_dir: Path = FICHAS_GENERADAS_DIR,
) -> ResultadoCarga:
    """Carga la ficha generada del paciente en Rayen.

    Pasos:
      1. Lee el archivo del paso 7. Si no existe -> skip.
      2. Comparte el flujo de apertura con paso 3
         (`abrir_ficha_por_nombre`).
      3. Pega el contenido en el editor interno de Rayen.
      4. Devuelve el ResultadoCarga (el caller lo acumula en JSON).
    """
    resultado = ResultadoCarga(
        nombre=paciente.nombre,
        fecha=paciente.fecha,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )

    # 1) Leer el insumo del paso 7
    path = _path_ficha_generada(paciente.nombre, paciente.fecha, fichas_dir)
    texto = leer_ficha_generada(paciente.nombre, paciente.fecha, fichas_dir)
    if texto is None:
        logger.warning(
            f"[cargar_ficha] sin insumo: no existe {path.name} en {fichas_dir}"
        )
        resultado.estado = "skip"
        resultado.motivo = f"sin insumo: {path.name}"
        return resultado
    resultado.ficha_path = str(path)

    # 2) Abrir la ficha en Rayen (flujo compartido con paso 3)
    try:
        ok = abrir_ficha_por_nombre(driver, logger, paciente)
    except Exception as e:
        logger.exception(
            f"[cargar_ficha] error abriendo ficha de {paciente.nombre}: {e}"
        )
        resultado.estado = "error"
        resultado.motivo = f"apertura_ficha: {type(e).__name__}: {e}"
        return resultado
    if not ok:
        # No se encontro al paciente en la tabla del dia.
        resultado.estado = "skip"
        resultado.motivo = "paciente no encontrado en tabla del dia"
        return resultado
    resultado.abierta = True

    # Si el panel no cargo (REQ-030), NO intentamos pegar: el editor
    # interno tampoco estara.
    if not paciente.panel_cargo:
        resultado.estado = "error"
        resultado.motivo = "panel del paciente no cargo (REQ-030); editor no disponible"
        logger.error(f"[cargar_ficha] {resultado.motivo}")
        return resultado

    # 3) Pegar en el editor
    pegado = pegar_en_editor(driver, texto, logger)
    resultado.tipo_editor = pegado.tipo_editor.value
    if not pegado.ok:
        resultado.estado = "pendiente_selector" if "pendiente selector" in pegado.motivo else "error"
        resultado.motivo = pegado.motivo
        return resultado

    # Guardar (REQ-073 revisada 23-09-2026: guardado automatico).
    if not guardar_editor_anamnesis(driver, logger):
        resultado.estado = "error"
        resultado.motivo = "guardar: el editor no cerro tras presionar Guardar"
        logger.error(f"[cargar_ficha] {resultado.motivo}")
        return resultado

    # Verificacion post-guardado: reabrir el editor y comparar el
    # contenido contra la ficha generada (la anamnesis completa debe
    # quedar cargada en Rayen). Solo lectura: no se vuelve a guardar.
    textarea = abrir_editor_anamnesis(driver, logger)
    if textarea is not None:
        contenido_rayen = textarea.get_attribute("value") or ""
        if _normalizar_contenido(contenido_rayen) != _normalizar_contenido(texto):
            resultado.estado = "error"
            resultado.motivo = (
                "verificacion post-guardado: el contenido de Rayen difiere "
                "de la ficha generada"
            )
            logger.error(f"[cargar_ficha] {resultado.motivo}")
            return resultado
        logger.info("[cargar_ficha] verificacion post-guardado OK")
        # El editor reabierto se deja asi (sin cambios pendientes: solo
        # se leyo). La salida al siguiente paciente es por el menu
        # lateral 'Pacientes citados' (volver_a_pacientes_citados).
        # Regla de la usuaria: nunca se presionan botones de cerrar.
    else:
        logger.warning(
            "[cargar_ficha] no se pudo reabrir el editor para verificar; "
            "el guardado se asume OK por el cierre del editor"
        )

    resultado.estado = "ok"
    resultado.caracteres_pegados = pegado.caracteres_pegados or len(texto)
    logger.info(
        f"[cargar_ficha] pegado OK: {paciente.nombre} | "
        f"tipo_editor={pegado.tipo_editor.value} | "
        f"{resultado.caracteres_pegados} chars"
    )
    return resultado


# ---- Iterador batch ----


def _abrir_sesion(credenciales: dict[str, str], logger: logging.Logger):
    """Login a Rayen. Devuelve el driver o None si fallo."""
    try:
        return run_login(credenciales, logger, headless=False)
    except Exception as e:
        logger.exception(f"[cargar_ficha] login fallo: {e}")
        return None


def iterar_pacientes(
    logger: logging.Logger,
    pacientes: list[PacienteObjetivo],
    credenciales: dict[str, str] | None = None,
    fichas_dir: Path = FICHAS_GENERADAS_DIR,
    max_abiertas: int = 8,
) -> list[ResultadoCarga]:
    """Procesa cada paciente gestionando el ciclo de sesion (REQ-081).

    Rayen soporta solo 8 fichas abiertas por sesion: al llegar al limite
    cierra el navegador, vuelve a loguear y sigue con el resto. Si un
    paciente falla, la corrida continua con el siguiente.
    """
    resultados: list[ResultadoCarga] = []
    driver = None
    abiertas = 0  # fichas abiertas en la sesion actual
    en_ficha = False  # venimos de abrir una ficha (no de un skip)

    def _error(nombre: str, fecha: str, motivo: str) -> ResultadoCarga:
        return ResultadoCarga(
            nombre=nombre,
            fecha=fecha,
            estado="error",
            motivo=motivo,
            timestamp=datetime.now().isoformat(timespec="seconds"),
        )

    for i, p in enumerate(pacientes, 1):
        logger.info(f"[cargar_ficha] ({i}/{len(pacientes)}) {p.nombre} ({p.fecha})")
        try:
            # Limite de Rayen: 8 fichas abiertas -> cerrar y re-loguear.
            if driver is not None and abiertas >= max_abiertas:
                logger.info(
                    "[cargar_ficha] limite de fichas abiertas: cerrando "
                    "sesion y volviendo a loguear..."
                )
                safe_quit(driver, logger)
                driver = None
                abiertas = 0
                en_ficha = False

            # Volver a la lista si venimos de una ficha abierta.
            if driver is not None and en_ficha:
                volver_a_pacientes_citados(driver, logger)
                en_ficha = False

            if driver is None:
                driver = _abrir_sesion(credenciales or {}, logger)
                if driver is None:
                    resultados.append(
                        _error(p.nombre, p.fecha, "login fallo")
                    )
                    for restante in pacientes[i:]:
                        resultados.append(
                            _error(restante.nombre, restante.fecha, "login fallo")
                        )
                    return resultados
                abiertas = 0

            r = cargar_ficha_de_paciente(driver, logger, p, fichas_dir=fichas_dir)
            abiertas += 1 if r.abierta else 0
            en_ficha = r.abierta
        except Exception as e:
            logger.exception(
                f"[cargar_ficha] excepcion no controlada con {p.nombre}: {e}"
            )
            r = _error(p.nombre, p.fecha, f"excepcion no controlada: {type(e).__name__}: {e}")
        resultados.append(r)
    if driver is not None:
        safe_quit(driver, logger)
    return resultados


# ---- Trazabilidad ----


def _escribir_trazabilidad(
    resultados: list[ResultadoCarga],
    modo: str,
    args_extras: dict,
    out_dir: Path = TRAZABILIDAD_CARGA_DIR,
) -> Path:
    """Escribe data/trazabilidad_carga/carga_<ts>.json con el detalle."""
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "modo": modo,
        "args": args_extras,
        "resumen": {
            "total": len(resultados),
            "ok": sum(1 for r in resultados if r.estado == "ok"),
            "skip": sum(1 for r in resultados if r.estado == "skip"),
            "error": sum(1 for r in resultados if r.estado == "error"),
            "pendiente_selector": sum(
                1 for r in resultados if r.estado == "pendiente_selector"
            ),
        },
        "resultados": [asdict(r) for r in resultados],
    }
    path = out_dir / f"carga_{ts}.json"
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


# ---- Main ----


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Cargar la ficha generada (paso 7) en Rayen. "
            "Por defecto procesa UN paciente (--paciente + --fecha). "
            "Con --todos procesa los pacientes del informe del mes en curso."
        )
    )
    parser.add_argument("--paciente", type=str, default=None)
    parser.add_argument("--fecha", type=str, default=None)
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Procesa los pacientes del informe del mes en curso (modo batch).",
    )
    parser.add_argument("--informe", type=Path, default=None)
    parser.add_argument("--user", type=str, default="yadira")
    parser.add_argument(
        "--fichas-dir",
        type=Path,
        default=FICHAS_GENERADAS_DIR,
        help="Directorio con los .md del paso 7 (default: data/fichas_generadas).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "NO abre Rayen. Solo verifica que existan los archivos del "
            "paso 7 para los pacientes del modo elegido, simula el "
            "resultado del pegado como 'pendiente_selector' (REQ-075) y "
            "escribe la misma trazabilidad JSON. Util para probar el "
            "CLI y la trazabilidad sin browser."
        ),
    )
    parser.add_argument(
        "--solo-apertura",
        action="store_true",
        help=(
            "Hace login, abre la ficha del paciente y verifica que "
            "aparezca el <div>Atencion actual</div> (limite del flujo "
            "compartido con paso 3). NO intenta pegar. Util para "
            "validar visualmente que el flujo llega al limite sin "
            "tocar el editor de Rayen."
        ),
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    if args.informe is None:
        args.informe = _informe_mes_actual_path()

    if args.todos and "_completo" in args.informe.name:
        parser.error(
            f"REFUSADO: {args.informe.name} es el informe ANUAL, "
            f"no se puede usar con --todos."
        )

    if not args.todos and (not args.paciente or not args.fecha):
        parser.error("Modo 1 paciente requiere --paciente y --fecha. O usa --todos.")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("cargar_ficha")

    # Credenciales (cargador unico: env USERS_<ID>_* > config/users.json)
    try:
        credentials = load_credentials(args.user)
    except (KeyError, ValueError) as e:
        logger.error(f"Error cargando credenciales: {e}")
        return 2
    logger.info(f"[cargar_ficha] credenciales OK para {args.user}")

    # Pacientes
    if args.todos:
        pacientes = parsear_informe(args.informe)
        logger.info(
            f"[cargar_ficha] modo --todos: {len(pacientes)} pacientes del informe {args.informe.name}"
        )
        modo = "todos"
    else:
        pacientes = [
            PacienteObjetivo(
                fecha=args.fecha,
                nombre=args.paciente,
                tipo_atencion="(no se valida contra informe)",
                razon="",
            )
        ]
        logger.info(
            f"[cargar_ficha] modo 1 paciente: {pacientes[0].nombre} | {pacientes[0].fecha}"
        )
        modo = "un_paciente"

    # Login: en el modo completo lo gestiona iterar_pacientes (ciclo de
    # sesion cada 8 fichas, REQ-081). --solo-apertura abre su propia
    # sesion aqui. --dry-run no toca Rayen.
    driver = None
    if args.solo_apertura:
        try:
            driver = run_login(credentials, logger, headless=False)
        except Exception as e:
            logger.exception(f"[cargar_ficha] login fallo: {e}")
            return 3

    resultados: list[ResultadoCarga] = []
    try:
        if args.dry_run:
            logger.info("[cargar_ficha] DRY-RUN: sin Rayen, sin pegado real")
            for p in pacientes:
                path = _path_ficha_generada(p.nombre, p.fecha, args.fichas_dir)
                texto = leer_ficha_generada(p.nombre, p.fecha, args.fichas_dir)
                if texto is None:
                    resultados.append(
                        ResultadoCarga(
                            nombre=p.nombre,
                            fecha=p.fecha,
                            estado="skip",
                            motivo=f"sin insumo: {path.name}",
                            timestamp=datetime.now().isoformat(timespec="seconds"),
                        )
                    )
                else:
                    resultados.append(
                        ResultadoCarga(
                            nombre=p.nombre,
                            fecha=p.fecha,
                            ficha_path=str(path),
                            estado="pendiente_selector",
                            motivo="dry-run: REQ-075 pendiente",
                            tipo_editor="",
                            caracteres_pegados=0,
                            timestamp=datetime.now().isoformat(timespec="seconds"),
                        )
                    )
        elif args.solo_apertura:
            assert driver is not None  # este modo siempre pasa por login
            logger.info(
                "[cargar_ficha] SOLO-APERTURA: login + abrir ficha hasta "
                "<div>Atencion actual</div>; sin pegado"
            )
            for idx, p in enumerate(pacientes, 1):
                path = _path_ficha_generada(p.nombre, p.fecha, args.fichas_dir)
                texto = leer_ficha_generada(p.nombre, p.fecha, args.fichas_dir)
                if texto is None:
                    resultados.append(
                        ResultadoCarga(
                            nombre=p.nombre,
                            fecha=p.fecha,
                            estado="skip",
                            motivo=f"sin insumo: {path.name}",
                            timestamp=datetime.now().isoformat(timespec="seconds"),
                        )
                    )
                    continue
                try:
                    # Volver a la lista antes de cada paciente distinto del
                    # primero (mismo patron del iterador batch); el click
                    # en el sidebar es seguro desde cualquier pagina.
                    if idx > 1:
                        volver_a_pacientes_citados(driver, logger)
                    ok = abrir_ficha_por_nombre(driver, logger, p)
                except Exception as e:
                    resultados.append(
                        ResultadoCarga(
                            nombre=p.nombre,
                            fecha=p.fecha,
                            ficha_path=str(path),
                            estado="error",
                            motivo=f"apertura_ficha: {type(e).__name__}: {e}",
                            timestamp=datetime.now().isoformat(timespec="seconds"),
                        )
                    )
                    continue
                if not ok:
                    resultados.append(
                        ResultadoCarga(
                            nombre=p.nombre,
                            fecha=p.fecha,
                            ficha_path=str(path),
                            estado="skip",
                            motivo="paciente no encontrado en tabla del dia",
                            timestamp=datetime.now().isoformat(timespec="seconds"),
                        )
                    )
                    continue
                estado = "panel_logrado" if p.panel_cargo else "panel_no_cargo"
                motivo = (
                    "limite del flujo compartido (<div>Atencion actual</div>) "
                    "visible"
                    if p.panel_cargo
                    else "limite NO visible (panel no cargo en 60s)"
                )
                # Flujo de reemplazo (Yadira 24-09-2026), PASO A PASO:
                # descartar la anamnesis vieja (con guardia de respaldo) y
                # PARAR. El siguiente paso lo define la usuaria.
                if p.panel_cargo:
                    from src.rayen.escritura.editor_anamnesis import (
                        descartar_anamnesis,
                    )

                    base_ss = f"paso_{p.nombre.replace(' ', '_')}"
                    try:
                        from src.core.rutas import SCREENSHOTS_DIR as _SS

                        _SS.mkdir(parents=True, exist_ok=True)
                        driver.save_screenshot(
                            str(_SS / f"{base_ss}_1_atencion_actual.png")
                        )
                        logger.info(
                            "[cargar_ficha] paso 1: en Atencion actual "
                            "(screenshot guardado)"
                        )
                    except Exception:
                        pass

                    # Guardia: el respaldo de la anamnesis debe existir en
                    # OneDrive antes de descartar nada en Rayen.
                    respaldo = ANAMNESIS_DIR / (
                        f"anam_{safe_filename(p.nombre)}_{p.fecha}.md"
                    )
                    respaldo_ok = respaldo.exists()
                    if not respaldo_ok:
                        logger.error(
                            f"[cargar_ficha] sin respaldo ({respaldo.name}): "
                            f"NO se descarta la anamnesis en Rayen."
                        )
                        resultados.append(
                            ResultadoCarga(
                                nombre=p.nombre,
                                fecha=p.fecha,
                                ficha_path=str(path),
                                estado="error",
                                motivo=(
                                    "descartar bloqueado: sin respaldo en "
                                    f"OneDrive ({respaldo.name})"
                                ),
                                timestamp=datetime.now().isoformat(
                                    timespec="seconds"
                                ),
                            )
                        )
                        continue

                    descartado = descartar_anamnesis(
                        driver, logger, respaldo_existe=respaldo_ok
                    )
                    if descartado:
                        estado = "descartado"
                        motivo = (
                            "anamnesis vieja DESCARTADA (respaldo verificado "
                            "en OneDrive). PARADA aqui — el paso siguiente "
                            "(escritura de la ficha nueva) lo define la "
                            "usuaria."
                        )
                        try:
                            from src.core.rutas import SCREENSHOTS_DIR as _SS

                            driver.save_screenshot(
                                str(_SS / f"{base_ss}_2_descartado.png")
                            )
                            logger.info(
                                "[cargar_ficha] paso 2: anamnesis descartada "
                                "(screenshot guardado) — PARADA aqui"
                            )
                        except Exception:
                            pass

                        # Paso 3 (Yadira 24-09-2026): click en 'Agregar!'
                        # -> editor vacio para la ficha del LLM. PARADA:
                        # sin pegar todavia.
                        from src.rayen.escritura.editor_anamnesis import (
                            agregar_anamnesis_nueva,
                        )

                        textarea = agregar_anamnesis_nueva(driver, logger)
                        if textarea is not None:
                            estado = "editor_nuevo_logrado"
                            motivo = (
                                "'Agregar!' clickeado y editor VACIO abierto "
                                "(#historiaEnfermedad presente). PARADA aqui "
                                "— el pegado de la ficha y Guardar son el "
                                "paso siguiente."
                            )
                            try:
                                from src.core.rutas import SCREENSHOTS_DIR as _SS

                                driver.save_screenshot(
                                    str(_SS / f"{base_ss}_3_editor_nuevo.png")
                                )
                                logger.info(
                                    "[cargar_ficha] paso 3: editor nuevo "
                                    "abierto (screenshot) — PARADA aqui"
                                )
                            except Exception:
                                pass
                        else:
                            estado = "editor_nuevo_no_logrado"
                            motivo = (
                                "el boton 'Agregar!' o el editor no aparecieron"
                            )
                    else:
                        estado = "descarte_no_logrado"
                        motivo = (
                            "el descarte no se confirmo (ver logs; el "
                            "respaldo esta a salvo en OneDrive)"
                        )
                resultados.append(
                    ResultadoCarga(
                        nombre=p.nombre,
                        fecha=p.fecha,
                        ficha_path=str(path),
                        estado=estado,
                        motivo=motivo,
                        timestamp=datetime.now().isoformat(timespec="seconds"),
                    )
                )
        else:
            resultados = iterar_pacientes(
                logger,
                pacientes,
                credenciales=credentials,
                fichas_dir=args.fichas_dir,
            )
    finally:
        if driver is not None:
            with contextlib.suppress(Exception):
                safe_quit(driver, logger)

    # Trazabilidad
    args_extras = {
        "user": args.user,
        "informe": str(args.informe),
        "fichas_dir": str(args.fichas_dir),
        "dry_run": args.dry_run,
    }
    path_traz = _escribir_trazabilidad(resultados, modo, args_extras)
    logger.info(f"[cargar_ficha] trazabilidad -> {path_traz}")

    resumen = {
        "total": len(resultados),
        "ok": sum(1 for r in resultados if r.estado == "ok"),
        "skip": sum(1 for r in resultados if r.estado == "skip"),
        "error": sum(1 for r in resultados if r.estado == "error"),
        "pendiente_selector": sum(
            1 for r in resultados if r.estado == "pendiente_selector"
        ),
    }
    logger.info(f"[cargar_ficha] resumen: {resumen}")
    # Exit code: 0 si todo OK; 1 si hubo pendientes/errores. En
    # --solo-apertura, "panel_logrado" tambien es exito (ese era el
    # objetivo del modo).
    exitosos = resumen["ok"] + sum(
        1 for r in resultados if r.estado in ("panel_logrado", "editor_logrado")
    )
    return 0 if exitosos == resumen["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
