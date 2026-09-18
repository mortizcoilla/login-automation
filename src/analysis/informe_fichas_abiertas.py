"""Informe de fichas abiertas (estado = 'Iniciado') desde la DB local.

Lee `data/analysis/fichas_completo.db` (no requiere login a Rayen) y
muestra un informe con:
- Total de fichas abiertas
- Detalle: fecha, nombre, razón de la cita, tipo de atención
  (ordenado de la mas antigua a la mas reciente)
- Distribución por tipo de atención (resumen al final)

================================================================
DOS OPERACIONES ESTRICTAMENTE INDEPENDIENTES (regla 2026-09-09):
================================================================

(1) MENSUAL — informe del MES EN CURSO (default).
    Uso:  python -m src.analysis.informe_fichas_abiertas
    Out:  data/analysis/informe_fichas_abiertas_<MM-YYYY>.txt
    SQL:  WHERE fecha LIKE '%-<MM>-<YYYY>'
    Caso de uso: el trabajo diario de Yadira (Mortadelo, batch, etc.).

(2) ANUAL — informe del ANIO COMPLETO (--todos).
    Uso:  python -m src.analysis.informe_fichas_abiertas --todos
    Out:  data/analysis/informe_fichas_abiertas_<YYYY>_completo.txt
    SQL:  WHERE fecha LIKE '%-<YYYY>'
    Caso de uso: otros objetivos, NO el trabajo diario. Se corre
    cuando Miguel se dedique a tareas anuales (analisis historico,
    reportes regulatorios, etc.).

AISLAMIENTO (no negociable, sesion 2026-09-09):
- Distinto archivo de salida (sufijo MM-YYYY vs YYYY_completo).
- Distinto filtro SQL.
- Ninguna ruta modifica el archivo de la otra.
- Correr la anual NO toca el mensual, y viceversa.
- Si Miguel esta en el mensual, el archivo del mes en curso queda
  intacto aunque el se ponga a regenerar el anual.

Si en algun momento se necesita otro periodo (ej. julio 2026), se
puede usar --mes / --anio / --desde / --hasta; la salida tendra un
sufijo que NO colisiona ni con el mensual actual ni con el anual.

Privacidad: la DB tiene PII (nombre) y vive en data/analysis/ (en
.gitignore). Los archivos .txt de output tambien.
"""
from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DB_PATH = BASE_DIR / "data" / "analysis" / "fichas_completo.db"
OUT_DIR = BASE_DIR / "data" / "analysis"

# Sin columna "Plantilla" — removida por peticion de Yadira.
# Sin resolucion de plantilla canonica aqui.
from src.analysis.informe_paths import (  # noqa: E402
    informe_anual_path,
    informe_mes_actual_path,
)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Informe de fichas abiertas (estado Iniciado) desde DB local. "
            "Default: mes en curso. Con --todos: anio completo (operacion "
            "distinta, archivo separado)."
        )
    )
    p.add_argument(
        "--mes",
        type=int,
        help="Mes a filtrar (1-12). Default: mes en curso. NO usar junto con --todos.",
    )
    p.add_argument(
        "--anio",
        type=int,
        help="Anio a filtrar (ej 2026). Default: anio en curso.",
    )
    p.add_argument(
        "--desde",
        type=str,
        help="Fecha desde en formato dd-mm-yyyy. Default: inicio del mes/año seleccionado.",
    )
    p.add_argument(
        "--hasta",
        type=str,
        help="Fecha hasta en formato dd-mm-yyyy. Default: hoy.",
    )
    p.add_argument(
        "--todos",
        action="store_true",
        help=(
            "Ver TODO el anio (modo ANUAL). Operacion distinta, escribe a "
            "informe_fichas_abiertas_<YYYY>_completo.txt. NO toca el archivo "
            "mensual."
        ),
    )
    return p.parse_args()


def _es_modo_anual(args: argparse.Namespace) -> bool:
    """Decide si la operacion actual es ANUAL o MENSUAL.

    Anual = --todos y NO se paso --mes ni --desde/--hasta. Cualquier
    especificacion de mes o rango gana sobre --todos (el usuario pidio
    algo puntual, no el anio completo).
    """
    if not args.todos:
        return False
    if args.mes is not None:
        return False
    if args.desde or args.hasta:
        return False
    return True


def _resolver_periodo(args: argparse.Namespace) -> tuple[str, str, str, str]:
    """Devuelve (etiqueta_periodo, sql_where, params_tuple, sufijo_archivo).

    Tres modos, cada uno con sufijo unico:
    - ANUAL: --todos (sin --mes/--desde/--hasta) -> '<YYYY>_completo'
    - MENSUAL: --mes o default -> '<MM>-<YYYY>'
    - RANGO: --desde/--hasta -> '<desde>_a_<hasta>'
    """
    hoy = date.today()
    anio = args.anio if args.anio is not None else hoy.year

    if args.desde and args.hasta:
        etiqueta = f"{args.desde} a {args.hasta}"
        where = "estado = 'Iniciado' AND fecha BETWEEN ? AND ?"
        params = (args.desde, args.hasta)
        sufijo = f"{args.desde}_a_{args.hasta}"
    elif _es_modo_anual(args):
        etiqueta = f"anio {anio} (completo)"
        where = "estado = 'Iniciado' AND fecha LIKE ?"
        params = (f"%-{anio}",)
        sufijo = f"{anio}_completo"
    else:
        mes = args.mes if args.mes is not None else hoy.month
        etiqueta = f"{mes:02d}-{anio}"
        where = "estado = 'Iniciado' AND fecha LIKE ?"
        params = (f"%-{mes:02d}-{anio}",)
        sufijo = f"{mes:02d}-{anio}"

    return etiqueta, where, params, sufijo


def _cargar_fichas(where_sql: str, params: tuple) -> list[dict[str, str]]:
    if not DB_PATH.exists():
        print(f"ERROR: no existe la DB en {DB_PATH}", file=sys.stderr)
        return []
    conn = sqlite3.connect(DB_PATH)
    try:
        # Sesion 2026-09-09: ya no leemos 'razon' (Razon de la cita de
        # Rayen, sin valor clinico). En su lugar, el enriquecimiento
        # posterior llena 'motivo' desde la nota clinica.
        cur = conn.execute(
            f"SELECT fecha, nombre, tipo_atencion "
            f"FROM fichas WHERE {where_sql} "
            f"ORDER BY fecha ASC",
            params,
        )
        filas = [
            {
                "fecha": r[0] or "-",
                "nombre": r[1] or "-",
                "tipo_atencion": r[2] or "-",
            }
            for r in cur.fetchall()
        ]
    finally:
        conn.close()
    return filas


def _imprimir_informe(filas: list[dict[str, str]], periodo: str) -> None:
    print()
    print("=" * 180)
    print(f"INFORME DE FICHAS ABIERTAS — {periodo}")
    print("=" * 180)
    print(f"Total: {len(filas)} fichas en estado 'Iniciado'")
    print()

    if not filas:
        print("(sin fichas abiertas en este periodo)")
        print("=" * 140)
        return

    # Columnas del informe basico (paso 2 del pipeline).
    # 'Razon de la cita' se elimino en sesion 2026-09-09: era metadata
    # de Rayen sin valor clinico (siempre "Consulta" / "Control" /
    # "Espontanea"). En su lugar, el enriquecimiento posterior
    # (src/analysis/enriquecer_informe.py) llena 'motivo' desde la
    # nota clinica. La columna 'Edad' se llena desde la seccion
    # IDENTIFICACION de la nota.
    #
    # Orden de columnas:
    #   Fecha | Nombre | Edad | Tipo de atencion | Motivo
    # Edad y Motivo se imprimen como '(-)' cuando estan vacios (basico
    # sin enriquecer) para que el parser de enriquecer_informe.py
    # reciba SIEMPRE 5 partes y no se confunda con el formato viejo.
    cols = [
        ("fecha", "Fecha", 12),
        ("nombre", "Nombre", 32),
        ("edad", "Edad", 24),
        ("tipo_atencion", "Tipo de atencion", 32),
        ("motivo", "Motivo de la atencion", 24),
    ]
    header = "  ".join(f"{label:<{w}}" for _, label, w in cols)
    print(header)
    print("-" * len(header))
    for f in filas:
        # '(-)' en lugar de '' para que el parser siempre vea 5 partes.
        edad = f.get("edad") or "(-)"
        motivo = f.get("motivo") or "(-)"
        cells = [
            f"{f.get('fecha', '-'):<{12}}",
            f"{f.get('nombre', '-')[:32]:<{32}}",
            f"{edad[:24]:<{24}}",
            f"{f.get('tipo_atencion', '-')[:32]:<{32}}",
            f"{motivo[:24]:<{24}}",
        ]
        print("  ".join(cells))
    print("=" * 180)

    # Distribucion por tipo
    tipos: Counter = Counter(f["tipo_atencion"] for f in filas)
    print()
    print("Distribucion por tipo de atencion:")
    for tipo, cant in tipos.most_common():
        pct = 100 * cant / len(filas)
        print(f"  {tipo:<40s} {cant:3d}  ({pct:5.1f}%)")
    print("=" * 180)


class _TeeStdout:
    """Wrapper de stdout: duplica a consola y a un buffer en memoria."""

    def __init__(self, original: object) -> None:
        self._original = original
        self._buffer = io.StringIO()

    def write(self, s: str) -> int:
        self._original.write(s)  # type: ignore[union-attr]
        return self._buffer.write(s)

    def flush(self) -> None:
        self._original.flush()  # type: ignore[union-attr]

    def get_output(self) -> str:
        return self._buffer.getvalue()


def main() -> int:
    # Forzar UTF-8 en consola Windows (sino los guiones/tildes se ven como �)
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, OSError):
        pass

    args = _parse_args()
    periodo, where_sql, params, sufijo = _resolver_periodo(args)

    # Determinacion explicita del modo y del archivo que se va a escribir.
    # Esto hace visible al operador QUE archivo se esta tocando y cual NO,
    # evitando confusion entre la corrida mensual y la anual.
    modo_anual = _es_modo_anual(args)
    out_path = OUT_DIR / f"informe_fichas_abiertas_{sufijo}.txt"

    # Guard de aislamiento: el archivo destino NO debe colisionar con el
    # del OTRO modo. Si por algun motivo el sufijo calculado coincide con
    # un archivo del otro modo, abortar antes de escribir.
    otros_modos: list[Path] = []
    if modo_anual:
        # Estamos en anual: el archivo del mes en curso NO debe ser este.
        try:
            otros_modos.append(informe_mes_actual_path())
        except Exception:
            pass
    else:
        # Estamos en mensual/rango: el archivo anual NO debe ser este.
        try:
            otros_modos.append(informe_anual_path(anio=args.anio))
        except Exception:
            pass
    for otro in otros_modos:
        if out_path.resolve() == otro.resolve():
            print(
                f"ERROR: el archivo destino {out_path.name} colisiona con el "
                f"del otro modo ({otro.name}). Abortando para no pisarlo.",
                file=sys.stderr,
            )
            return 1

    # Banner de modo (transparencia operativa)
    if modo_anual:
        print(f"[modo ANUAL] archivo: {out_path.name}  (el mensual NO se toca)")
    else:
        print(f"[modo MENSUAL/rango] archivo: {out_path.name}  (el anual NO se toca)")

    tee = _TeeStdout(sys.stdout)
    sys.stdout = tee  # type: ignore[assignment]
    try:
        filas = _cargar_fichas(where_sql, params)
        _imprimir_informe(filas, periodo)
    finally:
        sys.stdout = tee._original  # type: ignore[assignment]

    # Persistir el output a archivo
    try:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path.write_text(tee.get_output(), encoding="utf-8")
        print(
            f"\n[output completo guardado en: {out_path.relative_to(BASE_DIR)}]"
        )
    except OSError as e:  # noqa: BLE001
        print(f"WARN: no se pudo guardar output: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
