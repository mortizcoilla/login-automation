"""Informe tecnico del procesamiento de notas clinicas.

La FICHA que se guarda en `notas_clinicas/` es para la doctora
(Yadira) y no debe contener informacion tecnica del proceso (rutas
absolutas, stacktraces, mensajes de error de OpenCV, etc.).

Este modulo genera un INFORME TECNICO separado (JSON) para Miguel,
que SI guarda el estado del proceso: por cada paciente, que se
extrajo, que fallo, que warnings hubo, cuanto tardo. Asi, si algo
falla en una corrida futura, se puede reconstruir que paso.

Uso:
    from src.tools.informe_tecnico import (
        WarningsCollector,
        generar_informe_tecnico,
    )

    collector = WarningsCollector()
    logging.getLogger("crear_notas").addHandler(collector)
    # ... loop de pacientes, snapshot por paciente ...
    informe = generar_informe_tecnico(...)
    informe.guardar(Path("data/analysis/informe_tecnico_20260823_1730.json"))
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


class WarningsCollector(logging.Handler):
    """Handler de logging que captura los mensajes en una lista.

    Pensado para uso por-paciente: se anade al logger "crear_notas",
    se hace un snapshot al inicio de cada paciente, y los warnings
    que aparezcan durante el procesamiento de ese paciente se pueden
    guardar en el informe tecnico.

    Para resetear entre pacientes: `collector.reset()`.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.records.append(msg)
        except Exception:  # noqa: BLE001
            # Nunca romper el flujo por un fallo en el handler.
            pass

    def reset(self) -> None:
        self.records = []

    def snapshot(self) -> list[str]:
        """Retorna la lista actual de warnings y la limpia."""
        actual = list(self.records)
        self.records = []
        return actual


@dataclass
class PacienteInforme:
    """Estado del procesamiento de UN paciente para el informe tecnico."""
    nombre: str
    fecha: str
    match_tipo: str = "ninguno"  # exacto | parcial | ambiguo | ninguno
    match_nombre_rayen: Optional[str] = None
    estado: str = "pendiente"  # ok | skipped | error
    extraccion: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    tiempo_segundos: float = 0.0


@dataclass
class InformeTecnico:
    """Informe tecnico completo de una corrida."""
    timestamp: str
    modo: str  # "todos" | "1_paciente"
    informe: str  # path al informe de fichas abiertas
    pacientes: list[PacienteInforme] = field(default_factory=list)
    resumen: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "modo": self.modo,
            "informe": self.informe,
            "pacientes": [
                {
                    "nombre": p.nombre,
                    "fecha": p.fecha,
                    "match_tipo": p.match_tipo,
                    "match_nombre_rayen": p.match_nombre_rayen,
                    "estado": p.estado,
                    "extraccion": p.extraccion,
                    "warnings": p.warnings,
                    "errores": p.errores,
                    "tiempo_segundos": p.tiempo_segundos,
                }
                for p in self.pacientes
            ],
            "resumen": self.resumen,
        }

    def guardar(self, ruta: Path) -> Path:
        """Guarda el informe como JSON. Crea el directorio si no existe."""
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return ruta


def generar_informe_tecnico(
    modo: str,
    informe: str,
    pacientes: list[PacienteInforme],
    stats: dict[str, int],
) -> InformeTecnico:
    """Crea el informe tecnico a partir de los datos recolectados."""
    warnings_total = sum(len(p.warnings) for p in pacientes)
    errores_total = sum(len(p.errores) for p in pacientes)
    resumen = {
        "objetivo": stats.get("procesados", 0),
        "abiertos": stats.get("abiertos", 0),
        "guardados": stats.get("guardados", 0),
        "saltados": stats.get("saltados", 0),
        "errores": stats.get("errores", 0),
        "warnings_total": warnings_total,
        "errores_tecnicos_total": errores_total,
    }
    return InformeTecnico(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        modo=modo,
        informe=informe,
        pacientes=pacientes,
        resumen=resumen,
    )


__all__ = [
    "InformeTecnico",
    "PacienteInforme",
    "WarningsCollector",
    "generar_informe_tecnico",
]
