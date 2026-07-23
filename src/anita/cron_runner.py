"""Cron runner para el reporte diario.

Uso desde cron de la mini PC Ubuntu (a las 19:00):

    0 19 * * * cd /opt/login-automation && /opt/login-automation/venv/bin/python -m src.anita.cron_runner

Por ahora solo imprime el reporte formateado. La integración con Telegram
queda pendiente hasta que resolvamos el bug del bot que no responde.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.anita.format_telegram import formatear_telegram
from src.anita.report_generator import generar_reporte
from src.queue_store import inicializar_db


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="anita-cron",
        description="Genera el reporte diario de gestión de fichas",
    )
    parser.add_argument(
        "--db",
        default="data/queue.db",
        help="Ruta a la base de datos SQLite de la cola",
    )
    parser.add_argument(
        "--fecha",
        default=None,
        help="Fecha del reporte (dd-mm-yyyy). Default: hoy.",
    )
    parser.add_argument(
        "--formato",
        choices=["telegram", "markdown", "json"],
        default="telegram",
        help="Formato de salida. Default: telegram (MarkdownV2).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No falla si la DB no existe todavía.",
    )
    args = parser.parse_args(argv)

    db_path = Path(args.db)
    if not db_path.exists():
        if args.dry_run:
            print(f"[anita] DB no existe en {db_path}, pero --dry-run activo. Saliendo OK.")
            return 0
        print(f"[anita] ERROR: DB no existe en {db_path}", file=sys.stderr)
        return 1

    inicializar_db(db_path)
    reporte = generar_reporte(str(db_path), args.fecha)

    if args.formato == "telegram":
        print(formatear_telegram(reporte))
    elif args.formato == "json":
        import json
        from dataclasses import asdict
        print(json.dumps(asdict(reporte), ensure_ascii=False, indent=2, default=str))
    else:  # markdown
        # Markdown estándar (no Telegram)
        print(f"# Reporte {reporte.fecha}\n")
        print(f"- Iniciadas: {reporte.total_iniciadas}")
        print(f"- Cerradas: {reporte.total_cerradas}")
        print(f"- Pendientes: {reporte.total_pendientes}")
        print(f"- Tasa de cierre: {reporte.tasa_cierre_pct}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
