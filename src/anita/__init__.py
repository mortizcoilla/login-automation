"""Anita — la reportera del equipo.

Genera el reporte diario de gestión de fichas. Corre a las 19:00 vía cron
desde la mini PC Ubuntu, y opcionalmente lo manda a Yadira por Telegram.

Anita NO es interactiva: solo produce reportes. Pilita la invoca cuando
Yadira pide el reporte, o el cron la llama cada noche.
"""

from src.anita.report_generator import generar_reporte, ReporteDiario
from src.anita.format_telegram import formatear_telegram

__all__ = ["generar_reporte", "ReporteDiario", "formatear_telegram"]
