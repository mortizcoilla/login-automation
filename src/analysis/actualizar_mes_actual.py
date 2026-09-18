"""CLI fino: la implementacion vive en src.informes.mes (Fase 4b).

Path estable para el flujo diario (REQ-008) y los agentes Mavis.
Mismo comando: python -m src analysis actualizar_mes_actual
"""

from __future__ import annotations

import sys

from src.informes.mes import main

if __name__ == "__main__":
    sys.exit(main())
