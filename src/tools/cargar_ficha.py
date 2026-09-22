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
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

with contextlib.suppress(AttributeError, OSError):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

from src.core.nombres import safe_filename
from src.core.rutas import FICHAS_GENERADAS_DIR, ROOT, TRAZABILIDAD_CARGA_DIR
from src.notas.modelos import PacienteObjetivo
from src.rayen.escritura.editor_anamnesis import (
    ResultadoPegado,
    TipoEditor,
    pegar_en_editor,
)
from src.rayen.flujos.apertura_ficha import abrir_ficha_por_nombre
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

sys.path.insert(0, str(ROOT))

USERS_CONFIG = ROOT / "config" / "users.json"


# ---- Carga de credenciales (mismo patron que crear_notas_clinicas) ----


def load_credentials(user_id: str) -> dict[str, str]:
    """Carga credenciales desde config/users.json."""
    if not USERS_CONFIG.exists():
        raise FileNotFoundError(f"No existe {USERS_CONFIG}")
    data = json.loads(USERS_CONFIG.read_text(encoding="utf-8"))
    users = data.get("users", {})
    if user_id not in users:
        raise ValueError(f"Usuario '{user_id}' no esta en {USERS_CONFIG}")
    credenciales: dict[str, str] = users[user_id]
    return credenciales


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
    motivo: str = ""
    tipo_editor: str = ""
    caracteres_pegados: int = 0
    timestamp: str = ""


# ---- Loader del archivo del paso 7 ----


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

    resultado.estado = "ok"
    resultado.caracteres_pegados = pegado.caracteres_pegados or len(texto)
    logger.info(
        f"[cargar_ficha] pegado OK: {paciente.nombre} | "
        f"tipo_editor={pegado.tipo_editor.value} | "
        f"{resultado.caracteres_pegados} chars"
    )
    return resultado


# ---- Iterador batch ----


def iterar_pacientes(
    driver,
    logger: logging.Logger,
    pacientes: list[PacienteObjetivo],
    fichas_dir: Path = FICHAS_GENERADAS_DIR,
) -> list[ResultadoCarga]:
    """Procesa cada paciente del informe. Continua con el siguiente si uno falla."""
    resultados: list[ResultadoCarga] = []
    for i, p in enumerate(pacientes, 1):
        logger.info(
            f"[cargar_ficha] ({i}/{len(pacientes)}) {p.nombre} ({p.fecha})"
        )
        try:
            r = cargar_ficha_de_paciente(driver, logger, p, fichas_dir=fichas_dir)
        except Exception as e:
            logger.exception(
                f"[cargar_ficha] excepcion no controlada con {p.nombre}: {e}"
            )
            r = ResultadoCarga(
                nombre=p.nombre,
                fecha=p.fecha,
                estado="error",
                motivo=f"excepcion no controlada: {type(e).__name__}: {e}",
                timestamp=datetime.now().isoformat(timespec="seconds"),
            )
        resultados.append(r)
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
            "resultado del pegado como 'pendiente_selector' (REQ-059) y "
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

    # Credenciales
    try:
        credentials = load_credentials(args.user)
    except (FileNotFoundError, ValueError) as e:
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

    # Login + iteracion (salteado en --dry-run).
    driver = None
    if not args.dry_run:
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
                            motivo="dry-run: REQ-059 pendiente",
                            tipo_editor="",
                            caracteres_pegados=0,
                            timestamp=datetime.now().isoformat(timespec="seconds"),
                        )
                    )
        elif args.solo_apertura:
            logger.info(
                "[cargar_ficha] SOLO-APERTURA: login + abrir ficha hasta "
                "<div>Atencion actual</div>; sin pegado"
            )
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
                    continue
                try:
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
                    "visible; paso 8 se detendria aqui sin pegar"
                    if p.panel_cargo
                    else "limite NO visible (panel no cargo en 60s)"
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
                driver, logger, pacientes, fichas_dir=args.fichas_dir
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
    # Exit code: 0 si todo OK; 1 si hubo pendientes/errores.
    return 0 if resumen["ok"] == resumen["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
