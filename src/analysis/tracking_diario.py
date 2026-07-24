"""Tracking diario de fichas 'Iniciado' — el verdadero backlog de Yadira.

Recorre día por día desde 01-01-2026 (o desde la fecha mínima
registrada en la DB si ya existe) hasta HOY, captura las fichas en
estado 'Iniciado' en cada día, y mantiene una tabla SQLite acumulativa:

    - ficha vista por primera vez → INSERT con primera_vista = día
    - ficha ya existente → UPDATE ultima_vista = día
    - (futuro) ficha que desaparece N días → marcar como cerrada

Output:
    - data/analysis/tracking.db (tabla fichas + runs)
    - Reporte en consola con: total abiertas hoy, distribución por tipo,
      fichas nuevas vs. actualizadas, top fichas más antiguas abiertas.

Privacidad: solo se persisten cita_id (numérico) y tipo_atencion
(texto). NO se guardan RUT, nombre ni observación.
"""
from __future__ import annotations

import io
import logging
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from src.constants import DATE_FORMAT
from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger
from src.pancho_skills import listar_iniciados, login_rayen

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "analysis" / "tracking.db"

# Fecha de inicio absoluta del recorrido
FECHA_INICIO_ABSOLUTA = date(2026, 1, 1)


def _init_db() -> sqlite3.Connection:
    """Crea la DB y las tablas si no existen."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS fichas (
            cita_id INTEGER PRIMARY KEY,
            tipo_atencion TEXT,
            fecha_primera_vista TEXT NOT NULL,
            fecha_ultima_vista TEXT NOT NULL,
            cerrada_el TEXT
        )
        """
    )
    # Migración liviana: si la tabla ya existía sin 'cerrada_el', agregarla.
    cur = conn.execute("PRAGMA table_info(fichas)")
    cols = {row[1] for row in cur.fetchall()}
    if "cerrada_el" not in cols:
        conn.execute("ALTER TABLE fichas ADD COLUMN cerrada_el TEXT")
        conn.commit()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha_run TEXT NOT NULL,
            fecha_inicio_recorrido TEXT NOT NULL,
            fecha_fin_recorrido TEXT NOT NULL,
            dias_recorridos INTEGER,
            fichas_nuevas INTEGER,
            fichas_actualizadas INTEGER
        )
        """
    )
    conn.commit()
    return conn


def _dias_habiles(inicio: date, fin: date) -> list[date]:
    """Devuelve la lista de días hábiles (lun-vie) entre inicio y fin inclusive."""
    dias: list[date] = []
    current = inicio
    while current <= fin:
        if current.weekday() < 5:  # 0=lun, 4=vie
            dias.append(current)
        current += timedelta(days=1)
    return dias


def _fecha_inicio_recorrido(conn: sqlite3.Connection) -> date:
    """Determina desde qué fecha hay que recorrer.

    - Primera vez: FECHA_INICIO_ABSOLUTA (01-01-2026)
    - Siguientes: la fecha más antigua entre las `fecha_primera_vista`
      registradas. Esto cubre el caso de una ficha que se cerró y
      volvió a abrirse.

    ⚠ Como las fechas están guardadas en formato dd-mm-yyyy (string),
    no se puede usar MIN() directamente (orden lexicográfico no es
    cronológico). Por eso las traigo todas y comparo en Python.
    """
    cur = conn.execute("SELECT fecha_primera_vista FROM fichas")
    fechas_str = [r[0] for r in cur.fetchall() if r[0]]
    if not fechas_str:
        return FECHA_INICIO_ABSOLUTA
    fechas = []
    for f in fechas_str:
        try:
            fechas.append(datetime.strptime(f, DATE_FORMAT).date())
        except ValueError:
            continue
    if not fechas:
        return FECHA_INICIO_ABSOLUTA
    return max(FECHA_INICIO_ABSOLUTA, min(fechas))


def _upsert_ficha(
    conn: sqlite3.Connection, cita_id: int, tipo: str, fecha_vista: str
) -> str:
    """Inserta o actualiza una ficha. Retorna 'nueva' o 'actualizada'."""
    cur = conn.execute(
        "SELECT 1 FROM fichas WHERE cita_id = ?", (cita_id,)
    )
    if cur.fetchone() is None:
        conn.execute(
            """INSERT INTO fichas (cita_id, tipo_atencion,
               fecha_primera_vista, fecha_ultima_vista)
               VALUES (?, ?, ?, ?)""",
            (cita_id, tipo, fecha_vista, fecha_vista),
        )
        return "nueva"
    conn.execute(
        """UPDATE fichas
           SET fecha_ultima_vista = ?,
               tipo_atencion = COALESCE(?, tipo_atencion)
           WHERE cita_id = ?""",
        (fecha_vista, tipo, cita_id),
    )
    return "actualizada"


def _safe_quit(driver, logger) -> None:
    try:
        from src.browser_automation import safe_quit
        safe_quit(driver, logger)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"No se pudo cerrar el browser: {e}")


def _ensure_session_alive(driver, credentials, logger):
    """Si la sesión expiró, re-loggea. Retorna el driver (puede ser uno nuevo)."""
    from src.browser_automation import _es_url_login
    if not _es_url_login(driver.current_url):
        return driver
    logger.warning("Sesión expiró (URL de login detectada). Re-logueando...")
    _safe_quit(driver, logger)
    return login_rayen(credentials, logger, headless=False)


class _TeeStdout:
    """Wrapper de stdout que duplica cada write a un buffer en memoria.

    Permite seguir viendo el output en consola (en vivo) y, al final,
    guardar el contenido completo a un archivo.
    """

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


def _guardar_output(capturado: str, sufijo: str) -> Path | None:
    """Guarda el output capturado a data/analysis/<sufijo>.txt."""
    if not capturado.strip():
        return None
    try:
        OUT_DIR = BASE_DIR / "data" / "analysis"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUT_DIR / f"tracking_{sufijo}.txt"
        with open(path, "w", encoding="utf-8") as f:
            f.write(capturado)
        return path
    except OSError as e:
        print(f"WARN: no se pudo guardar output: {e}", file=sys.stderr)
        return None


def _resolver_usuario() -> str | None:
    """El user_id es el primer argv que NO es un flag NI el valor de un flag."""
    KNOWN_FLAGS = {"--desde", "--hasta", "--historico"}
    cli_user = None
    skip_next = False
    for arg in sys.argv[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg in KNOWN_FLAGS:
            skip_next = True  # el siguiente argumento es el valor del flag
            continue
        if arg.startswith("--"):
            # flag desconocido — ignorar
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
        print(
            f"Hay {len(users)} usuarios: {users}. Usando '{users[0]}'.",
            file=sys.stderr,
        )
    return users[0]


def _parse_args() -> tuple[date | None, date | None, bool]:
    """Lee --desde, --hasta y --historico de CLI.

    Returns:
        (desde, hasta, historico).
        - Si --historico está presente, `desde` queda en None y el
          caller debe usar FECHA_INICIO_ABSOLUTA.
        - Si no, --desde tiene prioridad sobre auto-detección.
    """
    desde: date | None = None
    hasta: date | None = None
    historico = False
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--desde" and i + 1 < len(args):
            desde = datetime.strptime(args[i + 1], DATE_FORMAT).date()
            i += 2
        elif args[i] == "--hasta" and i + 1 < len(args):
            hasta = datetime.strptime(args[i + 1], DATE_FORMAT).date()
            i += 2
        elif args[i] == "--historico":
            historico = True
            i += 1
        else:
            i += 1
    return desde, hasta, historico


def _run(logger: logging.Logger) -> int:
    """Lógica principal del tracking. Retorna exit code."""
    print("=" * 60)
    print("TRACKING DIARIO DE FICHAS 'INICIADO'")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    conn = _init_db()
    desde_arg, hasta_arg, historico = _parse_args()
    if historico:
        # --historico: fuerza el recorrido desde FECHA_INICIO_ABSOLUTA
        # (01-01-2026), ignorando la auto-detección desde la DB.
        # Útil para la primera corrida histórica o para re-poblar
        # el año completo.
        inicio = FECHA_INICIO_ABSOLUTA
        print(
            f"[--historico] Forzando recorrido desde "
            f"{FECHA_INICIO_ABSOLUTA.strftime(DATE_FORMAT)} (ignorando DB)"
        )
    elif desde_arg:
        inicio = desde_arg
    else:
        inicio = _fecha_inicio_recorrido(conn)
    fin = hasta_arg or date.today()

    if inicio > fin:
        print(f"ERROR: fecha de inicio {inicio} es posterior a fin {fin}", file=sys.stderr)
        return 1

    dias = _dias_habiles(inicio, fin)
    print(
        f"Recorrido planificado: {inicio.strftime(DATE_FORMAT)} → "
        f"{fin.strftime(DATE_FORMAT)} ({len(dias)} días hábiles)"
    )
    print(f"DB: {DB_PATH.relative_to(BASE_DIR)}")
    print()

    if not dias:
        print("No hay días para recorrer (¿fecha de inicio en el futuro?).")
        return 0

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    total_nuevas = 0
    total_actualizadas = 0
    tipos_vistos_hoy: Counter = Counter()
    citas_vistas_en_este_run: set[int] = set()

    try:
        driver = login_rayen(credentials, logger, headless=False)
        print("[OK] Login realizado. Iniciando recorrido día por día...\n")

        for idx, dia in enumerate(dias, 1):
            fecha_str = dia.strftime(DATE_FORMAT)

            # Re-login defensivo: si la sesión murió entre el día anterior
            # y este, re-logueamos antes de seguir.
            try:
                driver = _ensure_session_alive(driver, credentials, logger)
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: re-login falló -> {e}")
                continue

            try:
                pacientes = listar_iniciados(driver, logger, fecha=fecha_str)
            except Exception as e:  # noqa: BLE001
                logger.error(f"{fecha_str}: error -> {e}")
                continue

            n_nuevas_dia = 0
            n_actualizadas_dia = 0
            for p in pacientes:
                # ⚠ El PacienteIniciado actual NO expone cita_id (sería
                # el ideal). Usamos un proxy sin PII: combinación de
                # hora + tipo + adjunto + razon. Funciona para dedup
                # mientras Yadira no reagende dentro del mismo día.
                # TODO: agregar cita_id real a PacienteIniciado.
                proxy_id = (
                    hash((p.hora, p.tipo_atencion, p.adjunto, p.razon))
                    & 0x7FFFFFFF
                )
                resultado = _upsert_ficha(
                    conn, proxy_id, p.tipo_atencion, fecha_str
                )
                if resultado == "nueva":
                    n_nuevas_dia += 1
                else:
                    n_actualizadas_dia += 1

                citas_vistas_en_este_run.add(proxy_id)
                if dia == fin:
                    tipos_vistos_hoy[p.tipo_atencion] += 1

            total_nuevas += n_nuevas_dia
            total_actualizadas += n_actualizadas_dia
            conn.commit()

            # Mostrar progreso cada 5 días o al final
            if idx % 5 == 0 or idx == len(dias):
                print(
                    f"  [{idx}/{len(dias)}] {fecha_str}: "
                    f"{len(pacientes)} Iniciado "
                    f"(nuevas:{n_nuevas_dia} actualizadas:{n_actualizadas_dia})"
                )

        # === Cierre de fichas no vistas en este run ===
        # Una ficha que estaba en la DB pero NO apareció en este recorrido
        # se considera cerrada. Marcamos cerrada_el = hoy.
        # Esto permite que la DB refleje el estado real: con el tiempo,
        # las fichas que Yadira cierra desaparecen del listado "Iniciado"
        # y se marcan como cerradas acá.
        hoy_str = fin.strftime(DATE_FORMAT)
        cur = conn.execute(
            "SELECT cita_id FROM fichas WHERE cerrada_el IS NULL"
        )
        fichas_en_db = {row[0] for row in cur.fetchall()}
        fichas_a_cerrar = fichas_en_db - citas_vistas_en_este_run
        if fichas_a_cerrar:
            placeholders = ",".join("?" * len(fichas_a_cerrar))
            conn.execute(
                f"""UPDATE fichas SET cerrada_el = ?
                    WHERE cita_id IN ({placeholders})
                    AND cerrada_el IS NULL""",
                [hoy_str, *fichas_a_cerrar],
            )
            conn.commit()
            print(
                f"\n[CIERRES] {len(fichas_a_cerrar)} fichas marcadas "
                f"como cerradas el {hoy_str} (no aparecieron en este run)"
            )

        # Registrar el run
        conn.execute(
            """INSERT INTO runs (fecha_run, fecha_inicio_recorrido,
               fecha_fin_recorrido, dias_recorridos, fichas_nuevas,
               fichas_actualizadas) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime(DATE_FORMAT),
                inicio.strftime(DATE_FORMAT),
                fin.strftime(DATE_FORMAT),
                len(dias),
                total_nuevas,
                total_actualizadas,
            ),
        )
        conn.commit()

        # Reporte final — queries SQL al estado real de la DB
        total_fichas_db = conn.execute(
            "SELECT COUNT(*) FROM fichas"
        ).fetchone()[0]
        total_abiertas = conn.execute(
            "SELECT COUNT(*) FROM fichas WHERE cerrada_el IS NULL"
        ).fetchone()[0]
        total_cerradas = conn.execute(
            "SELECT COUNT(*) FROM fichas WHERE cerrada_el IS NOT NULL"
        ).fetchone()[0]
        tipos_abiertas_rows = conn.execute(
            """SELECT tipo_atencion, COUNT(*) AS cant
               FROM fichas WHERE cerrada_el IS NULL
               GROUP BY tipo_atencion
               ORDER BY cant DESC"""
        ).fetchall()

        print()
        print("=" * 60)
        print("REPORTE FINAL")
        print("=" * 60)
        print(f"Recorrido:           {inicio.strftime(DATE_FORMAT)} → "
              f"{fin.strftime(DATE_FORMAT)}")
        print(f"Días hábiles:        {len(dias)}")
        print(f"Fichas nuevas:       {total_nuevas}")
        print(f"Fichas actualizadas: {total_actualizadas}")
        print(f"Total fichas en DB:  {total_fichas_db}")
        print(f"  -> abiertas:       {total_abiertas}")
        print(f"  -> cerradas:       {total_cerradas}")
        print()
        print(f"=== FICHAS ABIERTAS AL CIERRE DE ESTE RUN ===")
        print(f"Total: {total_abiertas}")
        if tipos_abiertas_rows:
            print("Distribución por tipo:")
            for tipo, cant in tipos_abiertas_rows:
                pct = 100 * cant / total_abiertas if total_abiertas else 0
                print(f"  {tipo:<40s} {cant:3d}  ({pct:5.1f}%)")
        print("=" * 60)
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error fatal: {e}")
        return 1
    finally:
        try:
            input("\nPresione Enter para cerrar el browser...")
        except EOFError:
            pass
        _safe_quit(driver, logger)
        conn.close()


def main() -> int:
    """Wrapper que captura stdout para guardar el output a archivo."""
    logger = setup_logger()
    tee = _TeeStdout(sys.stdout)
    sys.stdout = tee
    rc = 0
    sufijo = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        rc = _run(logger)
    finally:
        sys.stdout = tee._original
        out_path = _guardar_output(tee.get_output(), f"run_{sufijo}")
        if out_path is not None:
            print(
                f"\n[output completo guardado en: "
                f"{out_path.relative_to(BASE_DIR)}]"
            )
    return rc


if __name__ == "__main__":
    sys.exit(main())
