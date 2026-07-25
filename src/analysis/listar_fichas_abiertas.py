"""Listado completo de fichas 'Iniciado' para HOY, con todos los campos.

A diferencia de tracking_diario.py (que recorre el año y mide cierres),
este script hace un live check del día actual y muestra UNA TABLA con
todos los campos de la tabla de Rayen más las fechas de tracking
(fecha_ultima_vista, cerrada_el) que vienen de la DB local.

Output:
- Consola: tabla formateada con todos los campos
- Archivo: data/analysis/listado_<dd-mm-yyyy>.txt (persistente)

Privacidad: los nombres SOLO se imprimen en el output (consola + archivo
en .gitignore). NO se persisten en la DB.
"""
from __future__ import annotations

import io
import logging
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from src.constants import DATE_FORMAT
from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger
from src.pancho_skills import listar_iniciados, login_rayen

BASE_DIR = Path(__file__).resolve().parent.parent.parent
TRACKING_DB = BASE_DIR / "data" / "analysis" / "tracking.db"


def _resolver_usuario() -> str | None:
    """Lee el user_id del primer argv que no sea flag (compatible con --user)."""
    cli_user = None
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            continue
        cli_user = arg
        break
    users = list_known_users()
    if not users:
        print("ERROR: no hay usuarios configurados", file=sys.stderr)
        return None
    if cli_user:
        if cli_user not in users:
            print(f"ERROR: '{cli_user}' no está configurado", file=sys.stderr)
            return None
        return cli_user
    if len(users) > 1:
        print(f"Hay {len(users)} usuarios: {users}. Usando '{users[0]}'.",
              file=sys.stderr)
    return users[0]


def _cargar_tracking_db() -> dict[int, tuple[str, str | None]]:
    """Carga la DB de tracking y devuelve un dict proxy_id → (ultima_vista, cerrada_el)."""
    out: dict[int, tuple[str, str | None]] = {}
    if not TRACKING_DB.exists():
        return out
    try:
        conn = sqlite3.connect(TRACKING_DB)
        for row in conn.execute(
            "SELECT cita_id, fecha_ultima_vista, cerrada_el FROM fichas"
        ):
            out[int(row[0])] = (str(row[1]), row[2])
        conn.close()
    except sqlite3.Error as e:  # noqa: BLE001
        print(f"WARN: no se pudo leer {TRACKING_DB}: {e}", file=sys.stderr)
    return out


def _proxy_id(hora: str, tipo: str, adjunto: str, razon: str) -> int:
    """Mismo cálculo que tracking_diario.py para mantener compatibilidad."""
    return hash((hora, tipo, adjunto, razon)) & 0x7FFFFFFF


def _safe_quit(driver, logger) -> None:
    try:
        from src.browser_automation import safe_quit
        safe_quit(driver, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo cerrar el browser: {e}")


class _TeeStdout:
    def __init__(self, original):
        self._original = original
        self._buffer = io.StringIO()

    def write(self, s: str) -> int:
        self._original.write(s)
        return self._buffer.write(s)

    def flush(self) -> None:
        self._original.flush()

    def get_output(self) -> str:
        return self._buffer.getvalue()


def _imprimir_tabla(filas: list[dict[str, str]], hoy: str) -> None:
    """Imprime la tabla completa con todos los campos."""
    print()
    print("=" * 110)
    print(f"LISTADO DE FICHAS 'INICIADO' — {hoy}")
    print("=" * 110)
    print(f"Total: {len(filas)} fichas abiertas")
    print()
    # Columnas a mostrar (todos los campos de PacienteIniciado + tracking)
    cols = [
        ("hora", "Hora", 7),
        ("estado", "Estado", 10),
        ("nombre", "Nombre", 30),
        ("tipo_cupo", "Cupo", 10),
        ("llegada", "Lleg.", 6),
        ("llamada", "Llam.", 6),
        ("tipo_atencion", "Tipo atención", 32),
        ("adjunto", "Adjunto", 20),
        ("razon", "Razón", 25),
        ("fecha_ultima_vista", "Ult. visto", 12),
        ("cerrada_el", "Cerrada el", 12),
    ]
    header = "  ".join(f"{label:<{w}}" for _, label, w in cols)
    print(header)
    print("-" * len(header))
    for f in filas:
        cells = []
        for key, _, w in cols:
            val = f.get(key, "") or "-"
            cells.append(f"{val[:w]:<{w}}")
        print("  ".join(cells))
    print("=" * 110)


def _run(logger: logging.Logger) -> int:
    print("=" * 60)
    print("LISTADO COMPLETO DE FICHAS 'INICIADO' (HOY)")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    # Cargar DB de tracking (para enriquecer con ultima_vista / cerrada_el)
    tracking = _cargar_tracking_db()
    print(f"DB tracking: {len(tracking)} fichas registradas")

    driver = None
    pacientes: list = []
    hoy = datetime.now().strftime(DATE_FORMAT)
    try:
        driver = login_rayen(credentials, logger, headless=False)
        print(f"\nListando fichas 'Iniciado' para {hoy}...")
        pacientes = listar_iniciados(driver, logger, fecha=hoy)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error durante el listado: {e}")
        return 1
    finally:
        try:
            input("\nPresione Enter para cerrar el browser...")
        except EOFError:
            pass
        _safe_quit(driver, logger)

    if not pacientes:
        print()
        print(f"*** 0 fichas 'Iniciado' en {hoy} ***")
        print("¡Yadira está al día!")
        return 0

    # Construir filas completas con todos los campos + tracking
    filas: list[dict[str, str]] = []
    for p in pacientes:
        pid = _proxy_id(p.hora, p.tipo_atencion, p.adjunto, p.razon)
        ultima, cerrada = tracking.get(pid, ("-", "-"))
        filas.append({
            "hora": p.hora,
            "estado": p.estado,
            "nombre": p.nombre,
            "tipo_cupo": p.tipo_cupo,
            "llegada": p.llegada,
            "llamada": p.llamada,
            "razon": p.razon,
            "tipo_atencion": p.tipo_atencion,
            "adjunto": p.adjunto,
            "fecha_ultima_vista": ultima,
            "cerrada_el": cerrada or "-",
        })

    _imprimir_tabla(filas, hoy)
    return 0


def main() -> int:
    logger = setup_logger()
    tee = _TeeStdout(sys.stdout)
    sys.stdout = tee
    rc = 0
    try:
        rc = _run(logger)
    finally:
        sys.stdout = tee._original
        # Persistir el output completo
        try:
            OUT_DIR = BASE_DIR / "data" / "analysis"
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            hoy = datetime.now().strftime(DATE_FORMAT)
            out_path = OUT_DIR / f"listado_{hoy}.txt"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(tee.get_output())
            print(
                f"\n[output completo guardado en: "
                f"{out_path.relative_to(BASE_DIR)}]"
            )
        except OSError as e:  # noqa: BLE001
            print(f"WARN: no se pudo guardar output: {e}", file=sys.stderr)
    return rc


if __name__ == "__main__":
    sys.exit(main())
