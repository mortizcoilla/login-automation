"""Listado completo del día de Pacientes citados: TODAS las fichas,
TODOS los estados (Completado, Iniciado, Pendiente, Agendado, No se
Presentó, etc.). Trae todos los campos de la tabla.

A diferencia de listar_fichas_abiertas.py (que solo trae 'Iniciado'),
este script muestra el panorama completo del día. Útil para entender
el flujo de Yadira: cuántas se atendieron, cuántas quedaron abiertas,
cuántas no llegaron, etc.

Output:
- Consola: tabla formateada con todos los campos y agrupada por estado
- Archivo: data/analysis/fichas_<dd-mm-yyyy>.txt (persistente)

Privacidad: los nombres SOLO se imprimen en el output (consola + archivo
en .gitignore). NO se persisten en la DB.
"""
from __future__ import annotations

import io
import logging
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from src.browser_automation import (
    ensure_session_alive,
    extraer_datos_fila,
    get_pacientes_del_dia,
    select_date,
    sort_by_estado,
)
from src.constants import DATE_FORMAT
from src.credentials import list_known_users, load_credentials
from src.logger_config import setup_logger
from src.pancho_skills import login_rayen
from src.plantillas import sanitizar_tipo

BASE_DIR = Path(__file__).resolve().parent.parent.parent


def _resolver_usuario() -> str | None:
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


def _imprimir_seccion(
    titulo: str, filas: list[dict], hoy: str
) -> None:
    print()
    print("-" * 110)
    print(f"  {titulo}  ({len(filas)} fichas)")
    print("-" * 110)
    cols = [
        ("hora", "Hora", 7),
        ("nombre", "Nombre", 30),
        ("tipo_cupo", "Cupo", 10),
        ("llegada", "Lleg.", 6),
        ("llamada", "Llam.", 6),
        ("tipo_atencion", "Tipo atención", 32),
        ("adjunto", "Adjunto", 20),
        ("razon", "Razón", 25),
    ]
    header = "  ".join(f"{label:<{w}}" for _, label, w in cols)
    print(header)
    print("-" * len(header))
    for f in sorted(filas, key=lambda x: x.get("hora", "")):
        cells = []
        for key, _, w in cols:
            val = f.get(key, "") or "-"
            cells.append(f"{val[:w]:<{w}}")
        print("  ".join(cells))


def _run(logger: logging.Logger) -> int:
    print("=" * 60)
    print("LISTADO COMPLETO DE FICHAS DEL DÍA (TODOS LOS ESTADOS)")
    print("=" * 60)

    user_id = _resolver_usuario()
    if user_id is None:
        return 1

    try:
        credentials = load_credentials(user_id)
    except (KeyError, ValueError) as e:
        print(f"ERROR cargando credenciales: {e}", file=sys.stderr)
        return 1

    driver = None
    filas_por_estado: dict[str, list[dict]] = {}
    hoy = datetime.now().strftime(DATE_FORMAT)
    try:
        driver = login_rayen(credentials, logger, headless=False)
        print(f"\nListando TODAS las fichas para {hoy}...")

        if not ensure_session_alive(driver, logger):
            raise RuntimeError("La sesión de Rayen es inválida tras login.")

        select_date(driver, logger, fecha_str=hoy)
        sort_by_estado(driver, logger)

        rows = get_pacientes_del_dia(driver, logger)

        for row in rows:
            try:
                datos = extraer_datos_fila(row)
            except ValueError as e:
                logger.warning(f"Fila saltada por error: {e}")
                continue
            estado = datos.get("estado", "DESCONOCIDO")
            filas_por_estado.setdefault(estado, []).append({
                "hora": datos.get("hora", ""),
                "estado": estado,
                "nombre": datos.get("nombre", ""),
                "tipo_cupo": datos.get("tipo_cupo", ""),
                "llegada": datos.get("llegada", ""),
                "llamada": datos.get("llamada", ""),
                "razon": datos.get("razon", ""),
                "tipo_atencion": sanitizar_tipo(datos.get("tipo_atencion", "")),
                "adjunto": datos.get("adjunto", ""),
            })
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error durante el listado: {e}")
        return 1
    finally:
        try:
            input("\nPresione Enter para cerrar el browser...")
        except EOFError:
            pass
        _safe_quit(driver, logger)

    total = sum(len(v) for v in filas_por_estado.values())
    print()
    print("=" * 60)
    print(f"RESUMEN DEL DÍA — {hoy}")
    print("=" * 60)
    print(f"Total fichas citadas: {total}")
    if filas_por_estado:
        print("Distribución por estado:")
        counter = Counter()
        for estado, filas in filas_por_estado.items():
            counter[estado] = len(filas)
        for estado, cant in counter.most_common():
            pct = 100 * cant / total if total else 0
            print(f"  {estado:<25s} {cant:3d}  ({pct:5.1f}%)")

    # Imprimir secciones por estado, priorizando las que importan
    orden_prioridad = ["Iniciado", "Completado", "Pendiente", "Agendado", "No se Presentó"]
    estados_a_mostrar = orden_prioridad + [
        e for e in filas_por_estado if e not in orden_prioridad
    ]
    for estado in estados_a_mostrar:
        if estado in filas_por_estado:
            _imprimir_seccion(estado, filas_por_estado[estado], hoy)

    print()
    print("=" * 60)
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
        try:
            OUT_DIR = BASE_DIR / "data" / "analysis"
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            hoy = datetime.now().strftime(DATE_FORMAT)
            out_path = OUT_DIR / f"fichas_{hoy}.txt"
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
