"""Análisis histórico de fichas abiertas en Rayen APS.

Lee los snapshots diarios en `data/raw_responses/*.json` y produce
agregados por día hábil. El foco es el estado 'Iniciado' — la deuda
clínica real que Yadira debe atender. Otros estados se cuentan para
contextualizar.

Privacidad: este script SOLO emite conteos y distribuciones. Nunca
imprime RUT, nombre ni observación de pacientes. Los IDs de cita
se usan internamente para detectar arrastre, no salen al output.

Output:
- data/analysis/fichas_abiertas_historico.csv (una fila por día)
- Resumen en consola (volumen, top 10 días, distribución por tipo,
  arrastre entre días)
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent.parent
RAW_DIR = BASE_DIR / "data" / "raw_responses"
OUT_DIR = BASE_DIR / "data" / "analysis"
OUT_CSV = OUT_DIR / "fichas_abiertas_historico.csv"

# Estados que el sistema Rayen usa. Solo 'Iniciado' es nuestro foco
# (la deuda clínica real que Yadira atiende). Los otros se cuentan
# para contextualizar, pero NO son el objetivo.
#
# Hallazgo clave: 'Pendiente' son fichas no-asistidas que otra persona
# reagenda — confirmado por Yadira, no es nuestro foco.
ESTADO_OBJETIVO = "Iniciado"


def parse_file(path: Path) -> list[dict[str, Any]]:
    """Lee un archivo raw_responses y devuelve la lista de citas."""
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"WARN: {path.name}: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list):
        return []
    return data


def _tipo_atencion(item: dict[str, Any]) -> str:
    cupos = item.get("Cupos") or []
    if cupos and isinstance(cupos[0], dict):
        return cupos[0].get("TipoAtencion", "SIN_TIPO") or "SIN_TIPO"
    return "SIN_TIPO"


def analizar_dia(items: list[dict[str, Any]], date_str: str) -> dict[str, Any]:
    """Cuenta estados y analiza 'Iniciado' para un día.

    No intentamos detectar arrastre entre días: los snapshots de
    `raw_responses/` muestran cada cita en un único día (verificado
    empíricamente — IDs no reaparecen). El arrastre se mide con
    live check, no con histórico.
    """
    estados: Counter = Counter()
    tipos_en_iniciado: Counter = Counter()

    for item in items:
        estado = (item.get("EstadoCita") or {}).get("Nombre", "DESCONOCIDO")
        estados[estado] += 1
        if estado == ESTADO_OBJETIVO:
            tipos_en_iniciado[_tipo_atencion(item)] += 1

    return {
        "fecha": date_str,
        "total": sum(estados.values()),
        "estados": dict(estados),
        "iniciado": estados.get(ESTADO_OBJETIVO, 0),
        "tipos_iniciado": dict(tipos_en_iniciado),
    }


def main() -> int:
    if not RAW_DIR.exists():
        print(f"ERROR: no existe {RAW_DIR}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    archivos = sorted(RAW_DIR.glob("*.json"))
    print(f"Procesando {len(archivos)} archivos en {RAW_DIR.name}/...")

    resultados: list[dict[str, Any]] = []
    for path in archivos:
        items = parse_file(path)
        if items:
            resultados.append(analizar_dia(items, path.stem))

    if not resultados:
        print("No hay datos para analizar.")
        return 1

    # Orden cronológico: parseamos dd-mm-yyyy del nombre del archivo.
    from datetime import datetime
    resultados.sort(key=lambda r: datetime.strptime(r["fecha"], "%d-%m-%Y"))

    with open(OUT_CSV, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "fecha", "total", "iniciado", "completado",
                "agendado", "pendiente", "no_se_presento", "otros",
                "tipos_iniciado",
            ]
        )
        for r in resultados:
            estados = r["estados"]
            writer.writerow(
                [
                    r["fecha"], r["total"], r["iniciado"],
                    estados.get("Completado", 0),
                    estados.get("Agendado", 0),
                    estados.get("Pendiente", 0),
                    estados.get("No se Presentó", 0),
                    estados.get("otros", 0),
                    json.dumps(r["tipos_iniciado"], ensure_ascii=False),
                ]
            )
    print(f"CSV escrito en {OUT_CSV.relative_to(BASE_DIR)}")

    total = sum(r["total"] for r in resultados)
    total_iniciado = sum(r["iniciado"] for r in resultados)
    promedio = total_iniciado / len(resultados) if resultados else 0

    estados_total: Counter = Counter()
    for r in resultados:
        for k, v in r["estados"].items():
            estados_total[k] += v

    max_r = max(resultados, key=lambda r: r["iniciado"])
    min_r = min(resultados, key=lambda r: r["iniciado"])

    tipos_global: Counter = Counter()
    for r in resultados:
        for t, c in r["tipos_iniciado"].items():
            tipos_global[t] += c

    print()
    print("=" * 64)
    print("ANÁLISIS HISTÓRICO — FICHAS ABIERTAS (Estado='Iniciado')")
    print("=" * 64)
    print(f"Periodo:            {resultados[0]['fecha']} -> {resultados[-1]['fecha']}")
    print(f"Días analizados:    {len(resultados)}")
    print(f"Total citas:        {total}")
    print()
    print("Distribución por estado (todo el periodo):")
    for estado, cant in estados_total.most_common():
        pct = 100 * cant / total if total else 0
        marker = "  <-- FOCO" if estado == "Iniciado" else ""
        print(f"  {estado:<22s} {cant:5d}  ({pct:5.1f}%){marker}")
    print()
    print(f"INICIADO por día (deuda clínica):")
    print(f"  Promedio:         {promedio:.2f}")
    print(f"  Máximo:           {max_r['iniciado']:3d}  ({max_r['fecha']})")
    print(f"  Mínimo:           {min_r['iniciado']:3d}  ({min_r['fecha']})")
    print()
    if total_iniciado:
        print("Distribución de 'Iniciado' por tipo de atención:")
        for tipo, cant in tipos_global.most_common(10):
            pct = 100 * cant / total_iniciado
            print(f"  {tipo:<40s} {cant:5d}  ({pct:5.1f}%)")
    print()
    print("Top 10 días con más 'Iniciado':")
    print(f"  {'Fecha':<12} {'Iniciado':>8} {'Total':>8} {'%Iniciado':>10}")
    for r in sorted(resultados, key=lambda x: -x["iniciado"])[:10]:
        pct = 100 * r["iniciado"] / r["total"] if r["total"] else 0
        print(f"  {r['fecha']:<12} {r['iniciado']:>8} {r['total']:>8} {pct:>9.1f}%")
    print("=" * 64)
    print()
    print("NOTA: este análisis es sobre snapshots históricos. Cada cita")
    print("aparece en un único día en estos datos (verificado). Para")
    print("responder 'cuántas tengo abiertas HOY' se requiere live check")
    print("con `listar_iniciados` (Fase 2).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
