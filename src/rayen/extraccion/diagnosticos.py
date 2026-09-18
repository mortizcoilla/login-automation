"""Diagnosticos, actividades y profesionales de la atencion.

Split de crear_notas_clinicas (Fase 3c).
"""

from __future__ import annotations

import logging

from selenium.webdriver.remote.webdriver import WebDriver


def extraer_diagnosticos(driver: WebDriver, logger: logging.Logger) -> list[str]:
    """Extrae los diagnosticos de la atencion (decisiones clinicas de Yadira).

    Cada diagnostico vive en un <li id="diagnose-XXX"> con:
      - .textoverflow-container con el nombre
      - .badge con estados (Nueva, Principal, Confirmado, Sospecha)
      - .collapse-text-sub con "Clasificacion: F98" y la descripcion CIE-10

    Devuelve una lista de strings formateados, una por diagnostico.
    """
    logger.info("[crear_notas] Extrayendo diagnosticos...")
    js = r"""
    const items = document.querySelectorAll('li[id^="diagnose-"]');
    const out = [];
    items.forEach(li => {
        const nombreEl = li.querySelector('.textoverflow-container');
        const nombre = nombreEl ? (nombreEl.textContent || '').trim() : '';
        const badges = Array.from(li.querySelectorAll('.badge'))
            .map(b => (b.textContent || '').trim())
            .filter(b => b)
            .join(', ');
        const classifEl = li.querySelector('.collapse-text-sub');
        const classif = classifEl ? (classifEl.textContent || '').trim() : '';
        if (nombre || classif) {
            const badgeStr = badges ? ` [${badges}]` : '';
            out.push(`- ${nombre}${badgeStr}: ${classif}`);
        }
    });
    return out;
    """
    try:
        result = driver.execute_script(js)
        diagnosticos = [d for d in (result or []) if d]
        logger.info(f"[crear_notas] Diagnosticos extraidos: {len(diagnosticos)}")
        return diagnosticos
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo diagnosticos: {e}")
        return []


def extraer_actividades(driver: WebDriver, logger: logging.Logger) -> list[str]:
    """Extrae las actividades de la atencion."""
    logger.info("[crear_notas] Extrayendo actividades...")
    js = r"""
    const items = document.querySelectorAll('li[id^="activity-"]');
    return Array.from(items).map(li => {
        const el = li.querySelector('.textoverflow-container');
        return el ? (el.textContent || '').trim() : '';
    }).filter(x => x);
    """
    try:
        result = driver.execute_script(js)
        actividades = [a for a in (result or []) if a]
        logger.info(f"[crear_notas] Actividades extraidas: {len(actividades)}")
        return actividades
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo actividades: {e}")
        return []


def extraer_profesionales(driver: WebDriver, logger: logging.Logger) -> list[str]:
    """Extrae los profesionales que participaron en la atencion."""
    logger.info("[crear_notas] Extrayendo profesionales...")
    js = r"""
    const items = document.querySelectorAll('li[id^="multiProfessional-"]');
    return Array.from(items).map(li => {
        const celdas = li.querySelectorAll('.col-sm-12');
        const nombre = celdas[0] ? (celdas[0].textContent || '').trim() : '';
        const rol = celdas[1] ? (celdas[1].textContent || '').trim() : '';
        if (nombre && rol) return `- ${nombre} (${rol})`;
        if (nombre) return `- ${nombre}`;
        return '';
    }).filter(x => x);
    """
    try:
        result = driver.execute_script(js)
        profesionales = [p for p in (result or []) if p]
        logger.info(f"[crear_notas] Profesionales extraidos: {len(profesionales)}")
        return profesionales
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo profesionales: {e}")
        return []
