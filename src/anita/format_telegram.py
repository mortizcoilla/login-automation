"""Formatea el reporte para enviarlo por Telegram.

Telegram usa un subset de Markdown:
- *bold* (no **bold**)
- _italic_
- `code`
- ```code blocks```
- Sin headers (#). Usamos emoji + bold para destacar secciones.
- Sin tablas. Usamos listas con bullets.
- Escapar: _ * [ ] ( ) ~ ` > # + - = | { } . !
"""

from __future__ import annotations

from src.anita.report_generator import ReporteDiario


def _esc(s: str) -> str:
    """Escapa caracteres especiales de MarkdownV2 de Telegram.

    Pragmático: escapamos lo que rompe el render, dejamos lo que no
    (ej: `-` solo es especial al inicio de línea, y nosotros usamos
    bullets `•`; `.` y `!` son seguros en texto normal).
    """
    chars = r"_*[]()~`>#+=|{}"
    return "".join(f"\\{c}" if c in chars else c for c in str(s))


def formatear_telegram(reporte: ReporteDiario) -> str:
    """Convierte un ReporteDiario a texto MarkdownV2 de Telegram.

    El texto resultante está listo para enviar vía `bot.send_message(...)`
    con `parse_mode='MarkdownV2'`.
    """
    partes: list[str] = []

    # Encabezado
    partes.append(f"📊 *Reporte del día* — {_esc(reporte.fecha)}\n")

    # Resumen ejecutivo
    partes.append("*Resumen general*\n")
    partes.append(f"• Iniciadas: *{reporte.total_iniciadas}*")
    partes.append(f"• Cerradas: *{reporte.total_cerradas}*")
    partes.append(f"• Pendientes: *{reporte.total_pendientes}*")
    partes.append(f"• Tasa de cierre: *{reporte.tasa_cierre_pct}%*\n")

    # Por tipo de atención
    if reporte.por_tipo:
        partes.append("*Por tipo de atención*\n")
        for tipo, n in reporte.por_tipo.items():
            partes.append(f"• {_esc(tipo)}: {n}")
        partes.append("")

    # Por estado actual
    if reporte.por_estado:
        partes.append("*Estado actual de las fichas*\n")
        # (singular, plural) para cada estado
        nombres_estado: dict[str, tuple[str, str]] = {
            "DRAFT_GENERADO": ("en draft", "en draft"),
            "EN_REVISION_USER": ("esperando revisión", "esperando revisión"),
            "EN_CORRECCION": ("en corrección", "en corrección"),
            "APROBADO_PENDIENTE_ENVIO": (
                "aprobada, falta enviar",
                "aprobadas, falta enviar",
            ),
            "ENVIADO": ("enviada ✅", "enviadas ✅"),
            "DESCARTADO": ("descartada", "descartadas"),
        }
        for estado, n in reporte.por_estado.items():
            sing, plur = nombres_estado.get(estado, (estado, estado))
            etiqueta = sing if n == 1 else plur
            partes.append(f"• {n} ficha{'s' if n != 1 else ''} {etiqueta}")
        partes.append("")

    # Detalle de cierre
    if reporte.total_enviadas > 0 or reporte.total_rechazadas > 0:
        partes.append("*Resultado de cierre*\n")
        partes.append(f"• Enviadas: *{reporte.total_enviadas}*")
        partes.append(f"• Rechazadas: *{reporte.total_rechazadas}*")
        partes.append("")

    # Mensaje si no hubo actividad
    if reporte.total_iniciadas == 0:
        partes.append("_No se registraron fichas para este día\\._")

    return "\n".join(partes)
