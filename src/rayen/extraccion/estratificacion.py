"""Estratificacion ECICEP: badge G0-G3 del header + modal de diagnosticos.

REQ-024 (extraccion primero, cierre con Salir) y REQ-025 (badge en header
sin clase de color). Split de crear_notas_clinicas (Fase 3c).
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait

# ---- Paso 4.2.c: extraer estratificacion ECICEP (card + modal) ----

# Selectores del panel de estratificacion ECICEP. Rayen muestra, en una
# card lateral del paciente, un badge con el grupo de riesgo (G1/G2/G3 +
# label) y un link 'Ver todos los diagnosticos activos' que abre un modal
# con la lista completa separada en Agudos y Cronicos. Cada dx trae
# badges (G1/G2/G3, GES, Controlado/No Controlado, Sospecha/Confirmado),
# codigo CIE-10, descripcion y problema asociado.
_ESTRAT_CARD_SELECTOR = ".stratification-card"
_ESTRAT_BADGE_SELECTOR = "button[aria-haspopup='true'] span.badge.badge-pill"
_ESTRAT_MODAL_TRIGGER_SELECTOR = '[data-modal="activeDiagnosisModalOpen"]'
_ESTRAT_MODAL_SELECTOR = ".diagnosis-data-modal"
_ESTRAT_MODAL_CLOSE_SELECTORS = [
    # Selector canonico del boton "Salir" del modal de diagnosticos activos
    # (proporcionado por Yadira/Miguel, sesion 2026-08-26). Es el camino
    # garantizado para cerrar el modal sin dejar overlay ni popover.
    'button.orange-btn[data-modal="activeDiagnosisModalOpen"]',
    ".diagnosis-data-modal .close",
    ".diagnosis-data-modal [data-dismiss='modal']",
    ".modal.show .close",
]


def _modal_estratificacion_visible(driver: WebDriver) -> bool:
    """True si el modal de diagnosticos activos esta visible en el DOM."""
    try:
        modal = driver.find_element(By.CSS_SELECTOR, _ESTRAT_MODAL_SELECTOR)
        return modal.is_displayed()
    except Exception:
        return False


def _popover_estratificacion_visible(driver: WebDriver) -> bool:
    """True si el popover de estratificacion (.stratification-card) esta visible."""
    try:
        card = driver.find_element(By.CSS_SELECTOR, _ESTRAT_CARD_SELECTOR)
        return card.is_displayed()
    except Exception:
        return False


def _abrir_popover_estratificacion(driver: WebDriver, logger: logging.Logger) -> bool:
    """Hace click en el badge 'G1/G2/G3 Riesgo ...' del header para abrir
    el popover de estratificacion (.stratification-card).

    Sin el popover abierto, el link 'Ver todos los diagnosticos activos'
    (que vive DENTRO del popover) no es clickable.
    """
    try:
        # Selector mas especifico: el button del badge ECICEP tiene clase
        # unica `bg-transparent` (los demas dropdowns de Rayen usan otras
        # clases). Eso evita matchear botones de adjuntos / profesionales.
        badge = driver.find_element(
            By.CSS_SELECTOR, "button.bg-transparent[aria-haspopup='true'] span.badge.badge-pill"
        )
        logger.info(f"[crear_notas] Badge encontrado: texto={(badge.text or '').strip()!r}")
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", badge)
        time.sleep(0.3)
        try:
            badge.click()
        except Exception:
            driver.execute_script("arguments[0].click();", badge)
        # Esperar a que el popover sea visible
        try:
            WebDriverWait(driver, 5).until(
                lambda d: any(
                    c.is_displayed()
                    for c in d.find_elements(By.CSS_SELECTOR, _ESTRAT_CARD_SELECTOR)
                )
            )
        except TimeoutException:
            logger.warning("[crear_notas] Popover de estrat. no aparecio tras click")
            return False
        time.sleep(0.3)
        return True
    except Exception as e:
        logger.warning(f"[crear_notas] No se pudo abrir popover de estrat.: {e}")
        return False


def _abrir_modal_estratificacion(driver: WebDriver, logger: logging.Logger) -> bool:
    """Hace click en 'Ver todos los diagnosticos activos' para abrir el modal."""
    try:
        trigger = driver.find_element(By.CSS_SELECTOR, _ESTRAT_MODAL_TRIGGER_SELECTOR)
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", trigger)
        time.sleep(0.3)
        try:
            trigger.click()
        except Exception:
            driver.execute_script("arguments[0].click();", trigger)
        try:
            WebDriverWait(driver, 5).until(
                lambda d: any(
                    m.is_displayed()
                    for m in d.find_elements(By.CSS_SELECTOR, _ESTRAT_MODAL_SELECTOR)
                )
            )
        except TimeoutException:
            logger.warning("[crear_notas] Modal de estrat. no aparecio tras click")
            return False
        time.sleep(0.5)
        return True
    except Exception as e:
        logger.warning(f"[crear_notas] No se pudo abrir modal de estrat.: {e}")
        return False


def _cerrar_modal_estratificacion(driver: WebDriver, logger: logging.Logger) -> None:
    """Cierra el modal de diagnosticos activos. Best-effort."""
    for sel in _ESTRAT_MODAL_CLOSE_SELECTORS:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:
            continue
        for btn in btns:
            try:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(0.3)
                    return
            except Exception:
                continue
    with contextlib.suppress(Exception):
        driver.execute_script("document.querySelector('.modal-backdrop')?.click();")
    try:
        from selenium.webdriver.common.keys import Keys

        driver.find_element(By.CSS_SELECTOR, "body").send_keys(Keys.ESCAPE)
    except Exception:
        pass


def _cerrar_popover_estratificacion(driver: WebDriver, logger: logging.Logger) -> None:
    """Cierra el popover de estratificacion (.stratification-card) despues de
    haber abierto el modal. Sin esto, el popover queda visible y puede
    interceptar el click en 'Atencion actual' que viene despues, rompiendo
    la extraccion de anamnesis/diagnosticos/actividad/profesionales.

    Estrategia: toggle del badge (click de nuevo en el badge lo cierra
    porque Bootstrap dropdowns son toggle) + ESC como fallback.
    """
    try:
        # Si el popover esta visible, hacer click en el badge lo cierra
        # (toggle behavior de Bootstrap dropdowns)
        if _popover_estratificacion_visible(driver):
            try:
                badge = driver.find_element(
                    By.CSS_SELECTOR,
                    "button.bg-transparent[aria-haspopup='true'] span.badge.badge-pill",
                )
                driver.execute_script("arguments[0].click();", badge)
                time.sleep(0.3)
            except Exception:
                pass
        # Fallback: click en el body + ESC
        with contextlib.suppress(Exception):
            driver.execute_script("document.body.click();")
        try:
            from selenium.webdriver.common.keys import Keys

            driver.find_element(By.CSS_SELECTOR, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass
        time.sleep(0.3)
    except Exception as e:
        logger.warning(f"[crear_notas] No se pudo cerrar popover de estrat.: {e}")


# JS inline que lee la card de estratificacion: badge + fecha_inicio.
# Se separa del modal para poder leer la card aunque el modal falle
# al abrir (caso de paciente sin diagnosticos activos completos).
#
# IMPORTANTE — bug fix 2026-08-25:
# El badge "G1/G2/G3 Riesgo ..." esta en el HEADER de la pagina (junto
# al nombre del paciente), NO dentro de `.stratification-card` (el popover).
# El popover aparece como contenido DESPUE?S de hacer click en el badge.
# Buscar el badge dentro del popover daba null -> grupo vacio -> no se
# creaba el bloque ESTRATIFICACION ECICEP.
_ESTRAT_CARD_JS = r"""
const result = { grupo: null, grupo_label: null, fecha_inicio: null };

// El badge G0/G1/G2/G3 vive en el header de la pagina, al costado del
// dropdown del nombre del paciente. Esta dentro de un <button> con
// aria-haspopup="true" (que abre el .dropdown-menu con la .stratification-card).
// NO incluimos la clase de color (badge-warning / badge-success / badge-danger)
// porque Rayen usa distintos colores segun el grupo, y queremos matchear
// TODOS los grupos. Tampoco usamos un selector generico span.badge.badge-pill
// porque hay OTROS badges en la pagina (Confirmado / Repetida / Principal
// de los diagnosticos) que matchearian y romerian la extraccion.
// El match por texto con la regex ^(G[0-3]) ya filtra correctamente.
const badge = document.querySelector(
    "button[aria-haspopup='true'] span.badge.badge-pill"
);
if (badge) {
    const txt = (badge.textContent || '').trim();
    // 2026-08-25: el badge usa G0..G3 (G0 = sin riesgo / sin clasificar),
    // NO solo G1..G3 como asumi inicialmente. G0 es valido. G4+ NO existe.
    // El lookahead (?=\s|$) exige que el digito vaya seguido de espacio o
    // fin de cadena, para que "G10" no matchee como "G1" + "0".
    const m = txt.match(/^(G[0-3])(?=\s|$)(.*)$/);
    if (m) {
        result.grupo = m[1];
        result.grupo_label = (m[2] || '').trim() || null;
    }
}

// El popover (`.stratification-card`) tiene "Informacion riesgo" con
// "Fecha inicio" + "Diagnostico" (los visibles del top). Se lee aunque
// el popover este hidden, porque el contenido esta en el DOM de todos modos.
const card = document.querySelector('.stratification-card');
if (card) {
    const items = card.querySelectorAll('.list-group-item');
    items.forEach(li => {
        const divs = li.querySelectorAll(':scope > div');
        if (divs.length >= 2) {
            const label = (divs[0].textContent || '').trim().toLowerCase();
            if (label.indexOf('fecha inicio') !== -1) {
                result.fecha_inicio = (divs[1].textContent || '').trim();
            }
        }
    });
}
return result;
"""


# JS inline que lee el modal de diagnosticos activos y devuelve la lista
# separada en Agudos y Cronicos. Cada item trae:
#   - nombre, fecha
#   - codigo_cie10 (si tiene "Clasificacion: X") o problema (si tiene "Problema: ...")
#   - descripcion_cie10 (subtitulo CIE-10)
#   - referido_por (subdiv con font-size 0.8rem)
#   - badges (G1/G2/G3, GES, Controlado, No Controlado, Sospecha, Confirmado, ...)
_ESTRAT_MODAL_JS = r"""
const result = { agudos: [], cronicos: [] };
const modal = document.querySelector('.diagnosis-data-modal');
if (!modal) return result;

const sections = modal.querySelectorAll('ul.list-group-flush');
let currentSection = null;

sections.forEach(ul => {
    const label = ul.querySelector('label.diagnose-active');
    if (label) {
        const name = (label.textContent || '').trim();
        if (name === 'Agudos') currentSection = 'agudos';
        else if (name === 'Cr\u00f3nicos' || name === 'Cronicos') {
            currentSection = 'cronicos';
        } else {
            currentSection = null;
        }
    }
    if (!currentSection) return;

    ul.querySelectorAll('li.diagnose-active-item').forEach(li => {
        const titleEl = li.querySelector('.diagnose-active-title');
        if (!titleEl) return;

        const item = {
            nombre: (titleEl.textContent || '').trim(),
            fecha: '',
            codigo_cie10: null,
            descripcion_cie10: null,
            problema: null,
            referido_por: null,
            badges: []
        };

        const dateEl = li.querySelector('.diagnose-active-date');
        if (dateEl) item.fecha = (dateEl.textContent || '').trim();

        li.querySelectorAll('.badge').forEach(b => {
            const t = (b.textContent || '').trim();
            if (t) item.badges.push(t);
        });

        const codeEl = li.querySelector('.diagnose-active-code');
        if (codeEl) {
            const txt = (codeEl.textContent || '').trim();
            if (txt.indexOf('Clasificaci\u00f3n:') === 0) {
                const m = txt.match(/Clasificaci\u00f3n:\s*(\S+)/);
                if (m) item.codigo_cie10 = m[1];
            } else if (txt.indexOf('Problema:') === 0) {
                item.problema = txt.replace(/^Problema:\s*/, '').trim();
            }
        }
        const subtitleEl = li.querySelector('.diagnose-active-subtitle');
        if (subtitleEl) {
            item.descripcion_cie10 = (subtitleEl.textContent || '').trim();
        }
        // Problema: en dx con GES, el problema esta en un div hermano
        // del w-100 dentro de .stratification-container.
        const problemContainer = li.querySelector(
            '.stratification-container > div:not(.w-100)'
        );
        if (problemContainer && !item.problema) {
            const txt = (problemContainer.textContent || '').trim();
            if (txt.indexOf('Problema:') === 0) {
                item.problema = txt.replace(/^Problema:\s*/, '').trim();
            }
        }
        // Referido por: subdiv con font-size 0.8rem dentro de stratification-container
        const refEl = li.querySelector(
            '.stratification-container div[style*="font-size: 0.8rem"]'
        );
        if (refEl) {
            item.referido_por = (refEl.textContent || '').trim();
        }

        if (currentSection === 'agudos') result.agudos.push(item);
        else result.cronicos.push(item);
    });
});

return result;
"""


def _formatear_dx_estrat(dx: dict[str, Any]) -> list[str]:
    """Formatea un dx individual de la estratificacion como lineas de texto."""
    out: list[str] = []
    nombre = dx.get("nombre") or ""
    badges = dx.get("badges") or []
    badges_str = f" [{', '.join(badges)}]" if badges else ""
    out.append(f"- {nombre}{badges_str}")
    if dx.get("codigo_cie10"):
        out.append(f"  CIE-10: {dx['codigo_cie10']}")
    if dx.get("descripcion_cie10"):
        out.append(f"  Descripcion: {dx['descripcion_cie10']}")
    if dx.get("problema"):
        out.append(f"  Problema: {dx['problema']}")
    if dx.get("referido_por"):
        out.append(f"  {dx['referido_por']}")
    if dx.get("fecha"):
        out.append(f"  Fecha: {dx['fecha']}")
    return out


def formatear_estratificacion(estrat: dict[str, Any] | None) -> str:
    """Formatea un dict de estratificacion ECICEP para guardarlo en la nota.

    Devuelve string vacio si no hay datos (paciente sin estratificar).
    """
    if not estrat or not estrat.get("grupo"):
        return ""

    lineas: list[str] = []
    grupo = estrat.get("grupo", "")
    label = estrat.get("grupo_label") or ""
    grupo_str = f"{grupo} ({label})" if label else grupo
    lineas.append(f"Grupo: {grupo_str}")

    fecha = estrat.get("fecha_inicio")
    if fecha:
        lineas.append(f"Fecha inicio: {fecha}")
    lineas.append("")

    cronicos = estrat.get("cronicos") or []
    if cronicos:
        lineas.append(f"Diagnosticos cronicos ({len(cronicos)}):")
        for dx in cronicos:
            lineas.extend(_formatear_dx_estrat(dx))
        lineas.append("")

    agudos = estrat.get("agudos") or []
    if agudos:
        lineas.append(f"Diagnosticos agudos ({len(agudos)}):")
        for dx in agudos:
            lineas.extend(_formatear_dx_estrat(dx))
        lineas.append("")

    return "\n".join(lineas).rstrip()


def extraer_estratificacion_ecicep(driver: WebDriver, logger: logging.Logger) -> dict[str, Any]:
    """Extrae la estratificacion ECICEP del paciente desde la UI de Rayen.

    Lee:
    - Badge con grupo de riesgo (G1/G2/G3 + label, ej. 'G2 Riesgo moderado')
    - Fecha de inicio de la estratificacion
    - Lista completa de diagnosticos activos separados en Agudos y Cronicos
      (con badges G1/G2/G3, GES, Controlado/No Controlado, Sospecha/
      Confirmado, codigo CIE-10, descripcion, problema GES, referido por)

    Estrategia:
    1. Lee la card de estratificacion (badge + fecha_inicio). Si la card
       no existe, devuelve dict vacio (paciente sin estratificar).
    2. Si la card existe, intenta leer el modal de diagnosticos activos
       (puede estar ya en el DOM). Si no esta visible, hace click en el
       trigger 'Ver todos los diagnosticos activos' y espera a que se abra.
    3. Parsea Agudos y Cronicos desde el modal.
    4. Cierra el modal (best-effort) para no contaminar la UI para los
       extractores siguientes.

    Devuelve dict con keys: grupo, grupo_label, fecha_inicio, agudos,
    cronicos. Cada item de agudos/cronicos trae: nombre, fecha,
    codigo_cie10, descripcion_cie10, problema, referido_por, badges.
    """
    out: dict[str, Any] = {
        "grupo": None,
        "grupo_label": None,
        "fecha_inicio": None,
        "agudos": [],
        "cronicos": [],
    }

    try:
        card_data = driver.execute_script(_ESTRAT_CARD_JS) or {}
    except Exception as e:
        logger.warning(f"[crear_notas] Error leyendo card de estratificacion: {e}")
        return out

    if not card_data.get("grupo"):
        logger.info(
            "[crear_notas] Paciente sin badge de estratificacion ECICEP "
            "(puede no estar estratificado aun)"
        )
        return out

    out["grupo"] = card_data.get("grupo")
    out["grupo_label"] = card_data.get("grupo_label")
    out["fecha_inicio"] = card_data.get("fecha_inicio")

    # Abrir el popover primero (click en el badge del header). Sin esto,
    # el link "Ver todos los diagnosticos activos" (que vive DENTRO del
    # popover) no es clickable.
    if not _popover_estratificacion_visible(driver):
        logger.info("[crear_notas] Abriendo popover de estratificacion (click badge)...")
        if not _abrir_popover_estratificacion(driver, logger):
            logger.warning(
                "[crear_notas] No se pudo abrir el popover. Solo se extraera badge + fecha_inicio."
            )
            return out

    if not _modal_estratificacion_visible(driver):
        logger.info("[crear_notas] Abriendo modal de diagnosticos activos para estratificacion...")
        if not _abrir_modal_estratificacion(driver, logger):
            logger.warning(
                "[crear_notas] No se pudo abrir el modal de estrat. "
                "Solo se extraera badge + fecha_inicio."
            )
            return out

    try:
        modal_data = driver.execute_script(_ESTRAT_MODAL_JS) or {}
        out["agudos"] = modal_data.get("agudos") or []
        out["cronicos"] = modal_data.get("cronicos") or []
    except Exception as e:
        logger.warning(f"[crear_notas] Error leyendo modal de estrat.: {e}")

    _cerrar_modal_estratificacion(driver, logger)
    _cerrar_popover_estratificacion(driver, logger)

    logger.info(
        f"[crear_notas] Estrat. ECICEP: grupo={out['grupo']} "
        f"agudos={len(out['agudos'])} cronicos={len(out['cronicos'])}"
    )
    return out
