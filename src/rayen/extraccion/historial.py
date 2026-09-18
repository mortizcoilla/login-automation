"""Historial de atenciones: extraccion y filtro de 6 meses (REQ-018).

Split de crear_notas_clinicas (Fase 3c).
"""

from __future__ import annotations

import logging
import re
from datetime import date as _date
from datetime import datetime

from selenium.webdriver.remote.webdriver import WebDriver


def _fecha_meses_atras(fecha: _date, meses: int) -> _date:
    """Devuelve fecha - N meses. Maneja wrap de año y clamping del dia al
    ultimo dia del mes destino (ej. 31-03 -> 31-09 no existe -> 30-09)."""
    total_months = fecha.year * 12 + (fecha.month - 1) - meses
    new_year, new_month = divmod(total_months, 12)
    new_month += 1
    # Clamping del dia
    import calendar as _cal

    max_day = _cal.monthrange(new_year, new_month)[1]
    new_day = min(fecha.day, max_day)
    return _date(new_year, new_month, new_day)


# REQ-018: historial limitado a los ultimos 6 meses; lo no parseable se conserva.
def filtrar_historial_ultimos_6_meses(
    historial: str,
    fecha_objetivo: str,
    logger: logging.Logger | None = None,
) -> str:
    """Filtra el historial de atenciones a solo las entradas dentro de los
    ultimos 6 meses respecto a fecha_objetivo (formato dd-mm-yyyy).

    Formato de entrada: lineas 'dd-mm-yyyy HH:MM ...' separadas por '\\n---\\n'.
    Lineas con fecha no parseable se conservan (no destruimos data por parsing).
    Si el historial es vacio o un placeholder ('(no se pudo...)', etc.),
    se devuelve tal cual sin filtrar.

    Devuelve el historial filtrado. Si tras filtrar queda vacio, devuelve
    '(sin atenciones en los ultimos 6 meses)'.
    """
    if not historial or not historial.strip():
        return historial
    # Placeholders / marcadores: pasar tal cual
    placeholders = (
        "(no se pudo extraer",
        "(sin historial",
        "(sin atenciones",
        "no tiene historial",
    )
    hist_lower = historial.lower()
    if any(p in hist_lower for p in placeholders):
        return historial

    # Parsear fecha objetivo
    try:
        fecha_obj = datetime.strptime(fecha_objetivo.strip(), "%d-%m-%Y").date()
    except (ValueError, AttributeError, TypeError):
        if logger:
            logger.warning(
                f"[crear_notas] No se pudo parsear fecha_objetivo={fecha_objetivo!r}, "
                f"se omite el filtro de 6 meses"
            )
        return historial

    fecha_corte = _fecha_meses_atras(fecha_obj, 6)

    lineas = [linea.strip() for linea in historial.split("\n---\n") if linea.strip()]
    out: list[str] = []
    descartadas = 0

    for linea in lineas:
        m = re.match(r"^(\d{2}-\d{2}-\d{4})", linea)
        if not m:
            out.append(linea)  # conservadora: conservar si no se puede parsear
            continue
        try:
            fecha_linea = datetime.strptime(m.group(1), "%d-%m-%Y").date()
        except ValueError:
            out.append(linea)
            continue
        if fecha_linea >= fecha_corte:
            out.append(linea)
        else:
            descartadas += 1

    if logger:
        logger.info(
            f"[crear_notas] Historial: {len(out)} entradas dentro de los ultimos "
            f"6 meses (corte={fecha_corte.strftime('%d-%m-%Y')}); "
            f"{descartadas} anteriores descartadas"
        )

    if not out:
        return "(sin atenciones en los ultimos 6 meses)"

    return "\n---\n".join(out)


def extraer_historial(driver: WebDriver, logger: logging.Logger) -> str:
    """Extrae el contenido de la seccion 'Historial de atenciones'.

    Solo queremos el contenido de las entradas (las filas del arbol),
    NO los filtros del sidebar (12 Meses, 24 Meses, etc.) que aparecen
    en el mismo panel.

    Estrategia:
    1) Subir desde h5.history-title-right hasta el panel que contiene
       el .rct-tree.
    2) Si ese tree no tiene entradas con fecha, hacer fallback: probar
       todos los .rct-tree de la pagina y elegir el que tenga mas
       entradas con fecha (descartando los filtros laterales).
    3) Si ningun tree tiene entradas, loguear el texto crudo de las
       primeras 3 .rct-node-clickable para diagnosticar.
    """
    logger.info("[crear_notas] Extrayendo historial de atenciones...")
    js = r"""
    const debug = {
        titulo_h5: document.querySelectorAll('h5.history-title-right').length,
        rct_trees_total: document.querySelectorAll('.rct-tree').length,
        rct_node_clickable_total: document.querySelectorAll('.rct-node-clickable').length,
        tree_mainText_total: document.querySelectorAll('.tree-mainText').length,
        panel_encontrado: false,
        panel_entradas: 0,
        pagina_entradas: 0,
    };
    const rxFecha = /^\d{2}-\d{2}-\d{4}/;

    // Helper: extraer entradas con fecha valida de un contenedor.
    function entradasConFecha(contenedor) {
        const nodes = contenedor.querySelectorAll('.rct-node-clickable');
        const lineas = [];
        nodes.forEach(entrada => {
            const fechaEl = entrada.querySelector('.tree-mainText span:first-child');
            if (!fechaEl) return;
            const f = (fechaEl.textContent || '').trim();
            if (!rxFecha.test(f)) return;
            const texto = (entrada.textContent || '').trim();
            if (texto) lineas.push(texto);
        });
        return lineas;
    }

    // Paso 1: buscar el panel subiendo desde h5.history-title-right.
    const titulo = document.querySelector('h5.history-title-right');
    let lineas = [];
    if (titulo) {
        let panel = titulo;
        for (let i = 0; i < 10; i++) {
            if (!panel.parentElement) break;
            panel = panel.parentElement;
            // Parar cuando encontremos un contenedor con .rct-node-clickable
            // o con .rct-tree (alguno de los dos puede estar presente).
            if (
                panel.querySelector('.rct-node-clickable') ||
                panel.querySelector('.rct-tree')
            ) {
                break;
            }
        }
        if (panel) {
            debug.panel_encontrado = true;
            lineas = entradasConFecha(panel);
            debug.panel_entradas = lineas.length;
        }
    }

    // Paso 2: fallback - si el panel no dio entradas, buscar en toda la pagina.
    if (lineas.length === 0) {
        const body = document.body || document.documentElement;
        lineas = entradasConFecha(body);
        debug.pagina_entradas = lineas.length;
    }

    if (lineas.length === 0) {
        // Sin entradas: loguear el texto de los primeros 3 .rct-node-clickable
        // para entender que tienen.
        const muestras = [];
        document.querySelectorAll('.rct-node-clickable').forEach((n, i) => {
            if (i < 3) {
                const span = n.querySelector('.tree-mainText span:first-child');
                muestras.push({
                    text: (n.textContent || '').trim().slice(0, 200),
                    span_text: span ? (span.textContent || '').trim() : null,
                });
            }
        });
        debug.muestras = muestras;
        return '__DEBUG__' + JSON.stringify(debug) + '__DEBUG__';
    }

    const resultado = lineas.join('\n---\n');
    return '__DEBUG__' + JSON.stringify(debug) + '__RESULT__' + resultado;
    """
    try:
        result = driver.execute_script(js) or ""
        logger.info(
            f"[crear_notas] historial JS retorno: len={len(result)} preview={result[:200]!r}"
        )
        if "__DEBUG__" in result:
            partes = result.split("__DEBUG__", 2)
            if len(partes) == 2:
                resto = partes[1]
                if "__RESULT__" in resto:
                    dbg, texto = resto.split("__RESULT__", 1)
                    logger.info(f"[crear_notas] DEBUG historial: {dbg}")
                else:
                    logger.info(f"[crear_notas] DEBUG historial (sin resultado): {resto}")
                    texto = ""
            else:
                texto = ""
        else:
            texto = result
        texto = texto.strip()
        if not texto or "No tiene historial" in texto:
            logger.info("[crear_notas] Historial: sin entradas para este paciente")
        else:
            logger.info(f"[crear_notas] Historial extraido: {len(texto)} chars")
        return texto
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo historial: {e}")
        return ""
