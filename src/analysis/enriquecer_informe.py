"""CLI fino: la implementacion vive en src.informes.enriquecer (Fase 4b).

Path estable para el flujo diario (REQ-008) y los agentes Mavis.
Mismo comando: python -m src analysis enriquecer_informe
"""

from __future__ import annotations

import sys

from src.informes.enriquecer import main

if __name__ == "__main__":
    sys.exit(main())
