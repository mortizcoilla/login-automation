"""Demo: genera un reporte de ejemplo para que se vea el output real.

Uso: python demo_reporte.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

# Asegurar que src/ está en el path cuando se corre como script
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import queue_store as qs
from src.anita.format_telegram import formatear_telegram
from src.anita.report_generator import generar_reporte
from src.queue_store import EstadoFicha, crear_ficha, inicializar_db


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "demo.db")
        inicializar_db(db)

        # Simular 8 fichas con distintos estados
        f1 = crear_ficha(db, "Karina Muñoz", "Control Crónico", "23-07-2026")
        f2 = crear_ficha(db, "Jorge Valenzuela", "Control Crónico", "23-07-2026")
        f3 = crear_ficha(db, "Carmen Ponce", "Control Integral ECICEP-G2", "23-07-2026")
        f4 = crear_ficha(db, "Pedro Soto", "Morbilidad", "23-07-2026")
        f5 = crear_ficha(db, "Ana Ruiz", "Morbilidad Telefónica", "23-07-2026")
        f6 = crear_ficha(db, "Luis Tapia", "Control Crónico", "23-07-2026")
        f7 = crear_ficha(db, "Marta Vega", "Ingreso ECICEP-G1", "23-07-2026")
        f8 = crear_ficha(db, "Roberto Díaz", "Consulta Salud Mental", "23-07-2026")

        # Estados — siguiendo las transiciones legales de la state machine
        for f in [f1, f2, f3]:
            qs.avanzar_estado(db, f.id, EstadoFicha.EN_REVISION_USER, "telegram:111", "M")
            qs.avanzar_estado(db, f.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "telegram:111", "A")
            qs.avanzar_estado(db, f.id, EstadoFicha.ENVIADO, "telegram:111", "E")
        qs.avanzar_estado(db, f4.id, EstadoFicha.EN_REVISION_USER, "telegram:111", "M")
        qs.avanzar_estado(db, f4.id, EstadoFicha.DESCARTADO, "telegram:111", "D")
        qs.avanzar_estado(db, f5.id, EstadoFicha.EN_REVISION_USER, "telegram:111", "M")
        qs.avanzar_estado(db, f5.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO, "telegram:111", "A")

        r = generar_reporte(db, "23-07-2026")
        print(formatear_telegram(r))
        return 0


if __name__ == "__main__":
    sys.exit(main())
