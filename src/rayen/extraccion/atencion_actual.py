"""Seccion "Atencion actual": motivo de consulta y anamnesis (REQ-026).

Split de crear_notas_clinicas (Fase 3c).
"""

from __future__ import annotations

import logging
import time

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import (
    expected_conditions as EC,  # noqa: N812 (alias estandar de Selenium)
)
from selenium.webdriver.support.ui import WebDriverWait


def click_atencion_actual(driver: WebDriver, logger: logging.Logger) -> bool:
    """Hace click en 'Atencion actual' y espera bloqueante a `li#anamnesis`.

    La anamnesis SIEMPRE existe en Rayen. Esta funcion espera bloqueante
    con WebDriverWait (timeout 8s) a que el panel de Evaluacion cargue tras
    el click. Si no carga, retorna False - el batch loop continua.
    """
    logger.info("[crear_notas] Click en 'Atencion actual'...")
    try:
        li = driver.find_element(
            By.XPATH,
            "//li[contains(@class, 'verticalnav-tab')]"
            "[.//div[normalize-space(text())='Atención actual']]",
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", li)
        time.sleep(0.3)
        try:
            li.click()
        except Exception:
            driver.execute_script("arguments[0].click();", li)
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "li#anamnesis"))
        )
        logger.info("[crear_notas] Click OK en 'Atencion actual', li#anamnesis presente")
        return True
    except TimeoutException:
        logger.warning(
            "[crear_notas] Panel Evaluacion no cargo en 8s. La anamnesis "
            "del paciente esta disponible en Rayen para revision manual."
        )
        return False
    except Exception as e:
        logger.warning(f"[crear_notas] No se encontro 'Atencion actual': {e}")
        return False


def extraer_motivo_consulta(driver: WebDriver, logger: logging.Logger) -> str:
    """Extrae el motivo de consulta/atencion de la nota de Yadira.

    En Rayen, dentro de `li#anamnesis` hay DOS `.textoverflow-container`:
    - El primero (directo, NO dentro de `.collapse-text-sub`) es el motivo
      corto, una sola linea. Visualmente tiene `style="height: 28px;"`.
    - El segundo esta dentro de `.collapse-text-sub` y es la anamnesis body.

    Tomamos el primero por POSICION (no por style attribute), porque el
    navegador puede normalizar el style y romper matchers tipo
    `[style*="height: 28px"]`.
    """
    logger.info("[crear_notas] Extrayendo motivo de consulta...")
    js = r"""
    const li = document.querySelector('li#anamnesis');
    if (!li) return '__NO_LI__';
    // Tomar todos los .textoverflow-container que NO esten dentro de
    // un .collapse-text-sub (esos son del body de la anamnesis).
    const candidatos = [];
    li.querySelectorAll('.textoverflow-container').forEach(el => {
        if (!el.closest('.collapse-text-sub')) {
            candidatos.push(el);
        }
    });
    if (candidatos.length === 0) {
        return '__NO_CANDIDATOS__';
    }
    return (candidatos[0].textContent || '').trim();
    """
    try:
        texto = driver.execute_script(js) or ""
        if texto == "__NO_LI__":
            logger.warning("[crear_notas] Motivo: li#anamnesis no existe en el DOM")
            return ""
        if texto == "__NO_CANDIDATOS__":
            logger.warning(
                "[crear_notas] Motivo: li#anamnesis existe pero no tiene "
                ".textoverflow-container fuera de .collapse-text-sub"
            )
            return ""
        texto = texto.strip()
        logger.info(f"[crear_notas] Motivo de consulta extraido: {len(texto)} chars")
        return texto
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo motivo de consulta: {e}")
        return ""


def extraer_anamnesis(driver: WebDriver, logger: logging.Logger) -> str:
    """Extrae especificamente la anamnesis (nota clinica de la doctora).

    Es el insumo principal: es la nota clinica que dejo Yadira y con la que
    Mortadelo debe llenar la plantilla. La anamnesis vive en `li#anamnesis`
    y su texto real esta en `.collapse-text-sub .textoverflow-container`.

    IMPORTANTE: el motivo de consulta es OTRO `.textoverflow-container` hermano
    (con style="height: 28px"), NO este. Por eso apuntamos al de adentro de
    `.collapse-text-sub` para no contaminar la anamnesis con el motivo.

    Usamos textContent via JavaScript para obtener TODO el texto del DOM,
    incluso el que esta visualmente truncado por el height del container.
    """
    logger.info("[crear_notas] Extrayendo anamnesis (nota clinica de Yadira)...")
    try:
        anamnesis_li = driver.find_element(By.CSS_SELECTOR, "li#anamnesis")
        # Diagnostico: que hay dentro de li#anamnesis ANTES del click ver_mas
        diag_inicial = driver.execute_script(
            """
            const li = document.querySelector('li#anamnesis');
            if (!li) return {existe: false};
            const colSubs = li.querySelectorAll('.collapse-text-sub');
            const conts = li.querySelectorAll('.textoverflow-container');
            const verMas = li.querySelector('.textoverflow-button');
            return {
                existe: true,
                collapse_text_sub_count: colSubs.length,
                textoverflow_container_count: conts.length,
                tiene_ver_mas: !!verMas,
                primer_colSub_text: colSubs[0] ? (colSubs[0].textContent || '').length : -1,
                primer_contenedor_text: conts[0] ? (conts[0].textContent || '').length : -1,
            };
            """
        )
        logger.info(f"[crear_notas] Diag anamnesis ANTES de ver_mas: {diag_inicial}")
        # Intentar expandir el "...ver mas" si existe, para asegurar que el
        # texto este visible y copiable
        try:
            ver_mas = anamnesis_li.find_element(By.CSS_SELECTOR, ".textoverflow-button")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", ver_mas)
            time.sleep(0.3)
            try:
                ver_mas.click()
            except Exception:
                driver.execute_script("arguments[0].click();", ver_mas)
            time.sleep(0.5)
        except Exception:
            # No hay boton "ver mas", probablemente ya esta expandido
            pass

        # Extraer el texto completo del contenedor de la anamnesis
        contenido = driver.execute_script(
            """
            const li = document.querySelector('li#anamnesis');
            if (!li) return '';
            const cont = li.querySelector('.collapse-text-sub .textoverflow-container');
            if (cont) return cont.textContent || '';
            // fallback: todo el li
            return li.textContent || '';
            """
        )
        # Diagnostico: que se leyo realmente
        logger.info(f"[crear_notas] Anamnesis extraida: {len((contenido or '').strip())} chars")
        contenido = (contenido or "").strip()
        logger.info(f"[crear_notas] Anamnesis extraida: {len(contenido)} chars")
        return contenido
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo anamnesis: {e}")
        return ""
