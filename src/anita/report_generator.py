"""Genera el reporte diario de gestión de fichas.

Lee del queue_store y produce un `ReporteDiario` con:
- Totales (iniciadas, cerradas, pendientes)
- Tasa de cierre
- Distribución por tipo de atención
- Conteo por estado de la state machine
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src import queue_store
from src.queue_store import EstadoFicha, Ficha


@dataclass
class ReporteDiario:
    fecha: str
    total_iniciadas: int
    total_cerradas: int
    total_enviadas: int
    total_rechazadas: int
    total_pendientes: int
    tasa_cierre_pct: float  # cerradas / iniciadas * 100
    por_tipo: dict[str, int] = field(default_factory=dict)
    por_estado: dict[str, int] = field(default_factory=dict)
    fichas: list[Ficha] = field(default_factory=list)


def generar_reporte(db_path: str, fecha: str | None = None) -> ReporteDiario:
    """Genera el reporte del día.

    Args:
        db_path: ruta a la base de datos de la cola.
        fecha: fecha en formato dd-mm-yyyy. Default: hoy.

    Returns:
        ReporteDiario con los datos calculados.
    """
    if fecha is None:
        fecha = datetime.now().strftime("%d-%m-%Y")

    metricas = queue_store.obtener_metricas_dia(db_path, fecha)
    fichas = queue_store.listar_fichas_hoy(db_path, fecha)

    # Conteos por estado
    por_estado: dict[str, int] = {e.value: 0 for e in EstadoFicha}
    for f in fichas:
        por_estado[f.estado.value] += 1

    # Conteos por tipo de atención
    por_tipo: dict[str, int] = {}
    for f in fichas:
        por_tipo[f.tipo_atencion] = por_tipo.get(f.tipo_atencion, 0) + 1

    iniciadas = metricas["total_iniciadas"]
    cerradas = metricas["total_cerradas"]
    tasa = (cerradas / iniciadas * 100) if iniciadas > 0 else 0.0
    pendientes = iniciadas - cerradas

    return ReporteDiario(
        fecha=fecha,
        total_iniciadas=iniciadas,
        total_cerradas=cerradas,
        total_enviadas=metricas["total_enviadas"],
        total_rechazadas=metricas["total_rechazadas"],
        total_pendientes=max(0, pendientes),
        tasa_cierre_pct=round(tasa, 1),
        por_tipo=dict(sorted(por_tipo.items(), key=lambda x: -x[1])),
        por_estado={k: v for k, v in por_estado.items() if v > 0},
        fichas=fichas,
    )
