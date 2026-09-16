# -*- coding: utf-8 -*-
"""Abre la ficha de UN paciente en Rayen.

Hace exactamente:
  1. Login en Rayen
  2. Navega hasta la pagina de Pacientes citados
  3. Selecciona la fecha indicada
  4. Busca al paciente por nombre completo
  5. Doble click sobre su nombre para abrir la ficha
  6. Se queda en la pantalla con la informacion del paciente

Ejemplo de uso (Monserrat):
    python -m src.tools.crear_notas_clinicas --paciente "Monserrat Sofia Delgado Ramirez" --fecha 05-08-2026

Reglas:
- Procesa UN SOLO paciente por ejecucion.
- Login con ventana visible para que el operador valide.
- No modifica nada fuera de este script.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass
from datetime import date as _date, datetime
from pathlib import Path
from typing import Any, Optional

from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# Forzar UTF-8 en consola Windows
try:
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from src.browser_automation import (
    ensure_session_alive,
    extraer_datos_fila,
    get_pacientes_del_dia,
    run_login,
    safe_quit,
    select_date,
    sort_by_estado,
)
from src.tools.informe_tecnico import (
    PacienteInforme,
    WarningsCollector,
    generar_informe_tecnico,
)


def _informe_mes_actual_path() -> Path:
    """Wrapper local para mantener el contrato con el resto del modulo.

    La implementacion real vive en `src.analysis.informe_paths` (single
    source of truth, sesion 2026-09-09).
    """
    from src.analysis.informe_paths import informe_mes_actual_path
    return informe_mes_actual_path()


INFORME_DEFAULT = _informe_mes_actual_path()
USERS_CONFIG = ROOT / "config" / "users.json"


# ---- Estructura del paciente objetivo ----

@dataclass
class PacienteObjetivo:
    """Un paciente del informe de fichas abiertas a procesar."""
    fecha: str
    nombre: str
    tipo_atencion: str
    razon: str = ""
    # Nombre real en Rayen. Se llena solo si difiere del nombre del
    # informe (caso de match parcial por truncamiento). El nombre del
    # informe sigue siendo el canonico para el filename; este campo
    # es solo metadato para que Mortadelo pueda matchear.
    nombre_rayen: Optional[str] = None
    # Sesion 2026-09-16: flag que paso_4_1_abrir_ficha setea segun si
    # el panel del paciente cargo o no. Si False, guardar_nota_clinica()
    # escribe una nota con placeholder + "REVISION MANUAL" para que
    # Yadira sepa que tiene que completar la ficha a mano.
    panel_cargo: bool = True


# ---- Carga de credenciales (reutiliza patron de main.py) ----

def load_credentials(user_id: str) -> dict[str, str]:
    """Carga credenciales desde config/users.json."""
    if not USERS_CONFIG.exists():
        raise FileNotFoundError(f"No existe {USERS_CONFIG}")
    data = json.loads(USERS_CONFIG.read_text(encoding="utf-8"))
    users = data.get("users", {})
    if user_id not in users:
        raise ValueError(f"Usuario '{user_id}' no esta en {USERS_CONFIG}")
    return users[user_id]


def list_known_users() -> list[str]:
    if not USERS_CONFIG.exists():
        return []
    data = json.loads(USERS_CONFIG.read_text(encoding="utf-8"))
    return list(data.get("users", {}).keys())


# ---- Parser del informe de fichas abiertas ----

def parsear_informe(ruta: Path) -> list[PacienteObjetivo]:
    """Lee el informe y devuelve la lista de pacientes objetivo.

    Mismo formato que usa mortadelo_batch._parsear_informe:
        dd-mm-yyyy  NOMBRE  TIPO_ATENCION  RAZON
    """
    if not ruta.exists():
        return []
    contenido = ruta.read_text(encoding="utf-8")
    # Prefijos que Rayen pone en el informe pero NO son parte del nombre
    # real del paciente. Hay que quitarlos para que el match contra
    # la tabla de Rayen funcione (alli aparece solo el nombre limpio).
    prefijo_patron = re.compile(
        r"^\s*\(?\s*(atenci[oó]n preferente|prioritario|urgente)\s*\)?\s*",
        re.IGNORECASE,
    )
    # Sesion 2026-09-09: el informe ahora puede traer la columna Edad
    # entre Nombre y Tipo. El regex anterior (`[A-Za-z]` para el 3er
    # campo) hacia backtracking e INCLUIA el "(-)" de Edad dentro del
    # nombre, produciendo nombres corruptos como
    # "Lisette Jara Gajardo              (-)" que Rayen no encuentra.
    # Migramos a re.split() y asignamos segun el conteo de columnas.
    #   6 cols: Fecha | Nombre | Edad | Tipo | Motivo | Plantilla
    #   5 cols: Fecha | Nombre | Tipo | Motivo | Plantilla (legacy)
    #   4 cols: Fecha | Nombre | Tipo | Plantilla (mas legacy)
    out: list[PacienteObjetivo] = []
    for line in contenido.splitlines():
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) < 4:
            continue
        if not re.match(r"^\d{2}-\d{2}-\d{4}$", parts[0]):
            continue
        fecha = parts[0]
        if len(parts) >= 6:
            nombre = parts[1]
            tipo_atencion = parts[3]
            motivo = parts[4]
        elif len(parts) == 5:
            nombre = parts[1]
            tipo_atencion = parts[2]
            motivo = parts[3]
        else:  # 4 cols (legacy, sin motivo)
            nombre = parts[1]
            tipo_atencion = parts[2]
            motivo = ""
        nombre_limpio = prefijo_patron.sub("", nombre).strip()
        out.append(
            PacienteObjetivo(
                fecha=fecha.strip(),
                nombre=nombre_limpio,
                tipo_atencion=tipo_atencion.strip(),
                razon=motivo.strip(),  # compat: 'razon' es el nombre del campo
            )
        )
    return out


# ---- Paso 4.1: filtrar por fecha, buscar nombre, doble click ----

def _buscar_paciente_en_tabla(
    driver: WebDriver,
    logger: logging.Logger,
    nombre_objetivo: str,
) -> Optional[tuple[object, Optional[str]]]:
    """Busca la fila del paciente por nombre en la tabla del dia.

    Devuelve una tupla (WebElement de la fila, nombre_real_rayen) si
    la encuentra, None si no.

    Si hubo match exacto, nombre_real_rayen es None (porque coincide
    con el nombre del informe). Si hubo match parcial, nombre_real_rayen
    tiene el nombre completo de Rayen (para guardarlo como metadato).

    Estrategia de match (en orden):
    1) Exacto: el nombre de Rayen es identico al del informe.
    2) Parcial unico: el nombre del informe esta contenido en el de
       Rayen (caso de informe truncado) o viceversa. Si hay UN solo
       candidato, matchea.
    3) Si hay multiples candidatos parciales, NO matchea para evitar
       falsos positivos.
    """
    rows = get_pacientes_del_dia(driver, logger)
    nombre_norm = nombre_objetivo.strip().lower()

    # 1) Match exacto.
    for row in rows:
        try:
            datos = extraer_datos_fila(row)
        except (ValueError, StaleElementReferenceException):
            # StaleElement: la fila se re-renderizo mientras iterabamos.
            # Saltamos y seguimos con las siguientes.
            continue
        if datos.get("nombre", "").strip().lower() == nombre_norm:
            return (row, None)

    # 2) Match parcial.
    candidatos: list[tuple[object, str]] = []
    for row in rows:
        try:
            datos = extraer_datos_fila(row)
        except (ValueError, StaleElementReferenceException):
            continue
        nombre_row = datos.get("nombre", "").strip()
        if not nombre_row:
            continue
        if nombre_norm in nombre_row.lower() or nombre_row.lower() in nombre_norm:
            candidatos.append((row, nombre_row))

    if len(candidatos) == 1:
        logger.info(
            f"[crear_notas] Match parcial: '{nombre_objetivo}' ~ "
            f"'{candidatos[0][1]}'"
        )
        return (candidatos[0][0], candidatos[0][1])
    if len(candidatos) > 1:
        nombres = [c[1] for c in candidatos]
        logger.warning(
            f"[crear_notas] Match parcial ambiguo para '{nombre_objetivo}': "
            f"{nombres}. No se hace match."
        )
        return None

    return None


def _doble_click_en_paciente(
    driver: WebDriver,
    logger: logging.Logger,
    row,
    nombre_objetivo: str | None = None,
) -> None:
    """Hace doble click en la fila del paciente para abrir la ficha.

    Si la fila quedo stale (Rayen re-renderizo la tabla mientras esperabamos),
    re-busca por nombre y re-intenta una vez. Sesion 2026-09-16: bug que
    afectaba ECICEP-g3 porque el panel tarda 15-30s en cargar y durante esa
    espera la fila original quedaba stale, haciendo fallar los 6 pacientes
    del mes con `StaleElementReferenceException`.
    """
    try:
        ActionChains(driver).double_click(row).perform()
        logger.info("[crear_notas] Doble click sobre la fila del paciente")
        return
    except StaleElementReferenceException:
        if not nombre_objetivo:
            # Sin nombre no podemos re-find. Propagamos el error original.
            logger.warning(
                "[crear_notas] Fila stale pero no se paso nombre para re-find"
            )
            raise
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] No se pudo doble-click en fila: {e}")
        raise

    # Stale + tenemos nombre: re-buscar y re-intentar una sola vez.
    logger.warning(
        "[crear_notas] Fila stale tras esperar panel (15-30s). "
        "Re-buscando por nombre..."
    )
    time.sleep(1)
    resultado = _buscar_paciente_en_tabla(driver, logger, nombre_objetivo)
    if resultado is None:
        raise RuntimeError(
            f"No se encontro '{nombre_objetivo}' tras stale element"
        )
    row_fresh, _ = resultado
    ActionChains(driver).double_click(row_fresh).perform()
    logger.info("[crear_notas] Doble click (re-find) OK")


# ---- Navegacion: volver a la lista de Pacientes citados ----

def volver_a_pacientes_citados(
    driver: WebDriver, logger: logging.Logger
) -> bool:
    """Hace click en el link 'Pacientes citados' del sidebar para volver
    a la lista. Sin esto, el script se queda pegado en la ficha del paciente.
    """
    try:
        link = driver.find_element(
            By.XPATH,
            "//a[contains(@href, '/main') and normalize-space(text())='Pacientes citados']",
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", link
        )
        time.sleep(0.3)
        try:
            link.click()
        except Exception:  # noqa: BLE001
            driver.execute_script("arguments[0].click();", link)
        time.sleep(1.5)
        logger.info("[crear_notas] Vuelta a 'Pacientes citados' OK")
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] No se pudo volver a 'Pacientes citados': {e}")
        return False


# ---- Limite de Rayen: solo se pueden abrir 8 fichas por sesion ----
MAX_FICHAS_POR_SESION = 8


# ---- Paso 4.2.b: verificar adjuntos (SIEMPRE, aunque no haya nada) ----

ADJUNTOS_DIR = ROOT / "notas_clinicas" / "_adjuntos"
# Directorio que Chrome usa para bajar archivos cuando se hace click
# en un attachment. Se setea en las prefs de Chrome (browser_automation.py).
# Mientras la descarga esta en curso, Chrome deja un .crdownload. Cuando
# termina, lo reemplaza por el archivo final con el nombre del servidor.
ADJUNTOS_DOWNLOAD_DIR = ADJUNTOS_DIR / "_chrome_dl"


def _normalizar_fecha(fecha_str: str) -> str:
    """Normaliza una fecha a dd-mm-yyyy para comparar."""
    if not fecha_str:
        return ""
    # Quitar hora si la tiene
    fecha_str = fecha_str.strip().split()[0] if fecha_str else ""
    # Si viene como yyyy-mm-dd, convertir
    for sep_in, sep_out in [("/", "-"), ("-", "-")]:
        if sep_in in fecha_str:
            partes = fecha_str.split(sep_in)
            if len(partes) == 3:
                if len(partes[0]) == 4:  # yyyy-mm-dd
                    return f"{partes[2]}-{partes[1]}-{partes[0]}"
                return fecha_str
    return fecha_str


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

    lineas = [l.strip() for l in historial.split("\n---\n") if l.strip()]
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


def detectar_adjuntos_en_historial(
    driver: WebDriver, logger: logging.Logger, fecha_objetivo: str
) -> list[dict[str, str]]:
    """Detecta adjuntos en el historial de atenciones."""
    logger.info(
        f"[crear_notas] Verificando adjuntos en historial (fecha objetivo={fecha_objetivo})..."
    )
    js = r"""
    const debug = {
        attachment_wrapper_total: document.querySelectorAll('.attachment-wrapper').length,
        rct_node_clickable_total: document.querySelectorAll('.rct-node-clickable').length,
        tree_mainText_total: document.querySelectorAll('.tree-mainText').length,
    };
    const result = [];
    const attachments = document.querySelectorAll('.attachment-wrapper');
    attachments.forEach(att => {
        const nombreEl = att.querySelector('.attachment-text');
        const nombre = nombreEl ? (nombreEl.textContent || '').trim() : '';
        let nodo = att.closest('.rct-node-clickable');
        let fechaTexto = '';
        if (nodo) {
            const fechaEl = nodo.querySelector('.tree-mainText span:first-child');
            if (fechaEl) fechaTexto = (fechaEl.textContent || '').trim();
        }
        let href = '';
        const aEl = att.closest('a') || att.querySelector('a');
        if (aEl) href = aEl.getAttribute('href') || '';
        if (!href) {
            const iEl = att.querySelector('i');
            if (iEl) {
                const aPadre = iEl.closest('a');
                if (aPadre) href = aPadre.getAttribute('href') || '';
            }
        }
        if (!href) {
            const allLinks = att.closest('div[onclick], a[href*="/"], div[data-href]');
            if (allLinks) {
                href = allLinks.getAttribute('href') ||
                       allLinks.getAttribute('data-href') || '';
            }
        }
        if (nombre) {
            result.push({
                nombre: nombre,
                fecha: fechaTexto,
                tamano: '',
                href: href || ''
            });
        }
    });
    return '__DEBUG__' + JSON.stringify(debug) + '__RESULT__' + JSON.stringify(result);
    """
    try:
        raw = driver.execute_script(js) or ""
        # Extraer debug y resultado
        result = []
        if "__RESULT__" in raw:
            dbg, payload = raw.split("__RESULT__", 1)
            logger.info(f"[crear_notas] DEBUG adjuntos: {dbg.replace('__DEBUG__', '')}")
            try:
                result = json.loads(payload)
            except Exception:  # noqa: BLE001
                result = []
        elif "__DEBUG__" in raw:
            logger.info(f"[crear_notas] DEBUG adjuntos: {raw.replace('__DEBUG__', '')}")
            result = []
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error buscando adjuntos: {e}")
        return []

    # Filtrar por fecha objetivo
    objetivo = _normalizar_fecha(fecha_objetivo)
    filtrados: list[dict[str, str]] = []
    for adj in result:
        fecha_adj = _normalizar_fecha(adj.get("fecha", ""))
        if fecha_adj == objetivo:
            filtrados.append(adj)
        else:
            logger.debug(
                f"[crear_notas] Adjunto ignorado por fecha: "
                f"{adj.get('nombre')} ({fecha_adj} != {objetivo})"
            )

    if filtrados:
        logger.info(
            f"[crear_notas] Adjuntos encontrados para {fecha_objetivo}: "
            f"{[a['nombre'] for a in filtrados]}"
        )
    else:
        logger.info(
            f"[crear_notas] Sin adjuntos para {fecha_objetivo} "
            f"(de {len(result)} totales en el historial, ninguno coincide)"
        )
    return filtrados


def descargar_adjunto(
    driver: WebDriver,
    logger: logging.Logger,
    adjunto: dict[str, str],
    fecha_objetivo: str,
) -> Optional[Path]:
    """Descarga un adjunto detectando la nueva pestaña que abre Rayen.

    En Rayen, hacer click en un .attachment-wrapper ABRE el archivo en
    una nueva pestaña (no usa el download manager de Chrome). Por eso
    esta funcion:
      1) Hace click en el wrapper.
      2) Espera a que aparezca una nueva pestana.
      3) Cambia a esa pestana y lee el contenido (URL directa o <img src>).
      4) Descarga el blob via requests (con cookies del WebDriver).
      5) Cierra la nueva pestana y vuelve a la principal.

    Devuelve el path local o None si no se pudo descargar.
    """
    import requests

    nombre = adjunto.get("nombre", "")
    if not nombre:
        logger.warning(f"[crear_notas] Adjunto sin nombre: {adjunto}")
        return None

    ADJUNTOS_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = _safe_filename(Path(nombre).stem)
    ext = Path(nombre).suffix or ".bin"
    out_path = ADJUNTOS_DIR / f"{safe_stem}_{fecha_objetivo}{ext}"
    if out_path.exists():
        logger.info(f"[crear_notas] Adjunto ya descargado: {out_path.name}")
        return out_path

    # 1) Marcar el wrapper con data-attribute para localizarlo con Selenium.
    try:
        marcado = driver.execute_script(
            """
            const nombre = arguments[0];
            const wrappers = document.querySelectorAll('.attachment-wrapper');
            for (const w of wrappers) {
                const txt = w.querySelector('.attachment-text');
                if (txt && (txt.textContent || '').trim() === nombre) {
                    w.setAttribute('data-mortadelo-target', '1');
                    w.scrollIntoView({block: 'center'});
                    return true;
                }
            }
            return false;
            """,
            nombre,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error marcando wrapper de {nombre}: {e}")
        return None

    if not marcado:
        logger.warning(
            f"[crear_notas] No encontre el wrapper de {nombre} para hacer click"
        )
        return None

    main_window = driver.current_window_handle
    windows_before = set(driver.window_handles)

    # 2) Click en el wrapper. ActionChains dispara la cadena completa
    #    de eventos que el handler de Rayen espera.
    try:
        wrapper = driver.find_element(
            By.CSS_SELECTOR,
            '.attachment-wrapper[data-mortadelo-target="1"]',
        )
        ActionChains(driver).move_to_element(wrapper).pause(0.2).click().perform()
        logger.info(f"[crear_notas] Click ActionChains sobre WRAPPER de {nombre}")
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[crear_notas] Error haciendo click sobre {nombre}: {e}"
        )
        try:
            driver.execute_script(
                "document.querySelectorAll('[data-mortadelo-target]')"
                ".forEach(e => e.removeAttribute('data-mortadelo-target'));"
            )
        except Exception:  # noqa: BLE001
            pass
        return None

    # Limpiar data-attribute (no esperamos al finally porque podemos
    # necesitar saltar a otra pestana).
    try:
        driver.execute_script(
            "document.querySelectorAll('[data-mortadelo-target]')"
            ".forEach(e => e.removeAttribute('data-mortadelo-target'));"
        )
    except Exception:  # noqa: BLE001
        pass

    # 3) Esperar a que se abra una nueva pestana.
    new_window: Optional[str] = None
    deadline = time.time() + 15
    while time.time() < deadline:
        nuevas = set(driver.window_handles) - windows_before
        if nuevas:
            new_window = next(iter(nuevas))
            break
        time.sleep(0.3)

    if new_window is None:
        logger.warning(
            f"[crear_notas] Click no abrio nueva pestana para {nombre}. "
            f"Probablemente Rayen cambio el handler."
        )
        return None

    # 4) Cambiar a la nueva pestana y obtener la URL del archivo.
    driver.switch_to.window(new_window)
    file_url = driver.current_url
    logger.info(f"[crear_notas] Nueva pestana abierta: {file_url}")

    # Si la URL no es directamente el archivo (ej. un visor HTML),
    # buscar el <img src> o el contenido del <iframe>.
    if not file_url.lower().split("?")[0].endswith(
        (".jpg", ".jpeg", ".png", ".pdf", ".gif", ".bmp", ".webp")
    ):
        try:
            img_src = driver.execute_script(
                """
                const img = document.querySelector('img');
                if (img && img.src) return img.src;
                const iframe = document.querySelector('iframe[src]');
                if (iframe) return iframe.src;
                return null;
                """
            )
            if img_src:
                file_url = img_src
                logger.info(f"[crear_notas] URL extraida del DOM: {file_url}")
        except Exception:  # noqa: BLE001
            pass

    # 5) Bajar el archivo via requests con cookies del WebDriver.
    cookies = driver.get_cookies()
    try:
        resp = requests.get(
            file_url,
            cookies={c["name"]: c["value"] for c in cookies},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=30,
        )
        resp.raise_for_status()
        out_path.write_bytes(resp.content)
        logger.info(
            f"[crear_notas] Adjunto descargado: {out_path.name} "
            f"({out_path.stat().st_size} bytes)"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[crear_notas] No se pudo descargar {nombre} desde {file_url}: {e}"
        )
        # Cerrar la nueva pestana igual y volver a la principal.
        try:
            driver.close()
            driver.switch_to.window(main_window)
        except Exception:  # noqa: BLE001
            pass
        return None

    # 6) Cerrar la nueva pestana y volver a la principal.
    try:
        driver.close()
        driver.switch_to.window(main_window)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error cerrando nueva pestana: {e}")

    return out_path


def procesar_adjuntos(
    driver: WebDriver,
    logger: logging.Logger,
    fecha_objetivo: str,
) -> str:
    """Verifica si hay adjuntos para la fecha objetivo.

    SIEMPRE se ejecuta. Si no hay nada, retorna string vacio (y no se
    agrega ninguna seccion al .txt). Si hay adjuntos, los descarga y
    los analiza con la skill `examenes` (easyocr para imagenes,
    pdfplumber para PDFs).

    Importante: la ficha que se guarda es para la doctora. Por lo
    tanto, NO incluye informacion tecnica del proceso (rutas
    absolutas, mensajes de error de OpenCV / easyocr / pdfplumber,
    stacktraces). Esos detalles van SOLO al log tecnico.
    """
    from src.mortadelo.skills.examenes import (
        detectar_tipo_examen,
        interpretar_audiometria,
        leer_examen,
    )

    adjuntos = detectar_adjuntos_en_historial(driver, logger, fecha_objetivo)
    if not adjuntos:
        # Regla: si no hay adjuntos, no pasa nada, se sigue adelante.
        return ""

    lineas: list[str] = []
    for adj in adjuntos:
        # Descargar
        local_path = descargar_adjunto(driver, logger, adj, fecha_objetivo)
        # Construir bloque de info (sin info tecnica)
        lineas.append(f"--- {adj.get('nombre', '?')} ---")
        lineas.append(f"Fecha atencion origen: {adj.get('fecha', '?')}")
        if local_path is not None:
            tamano_kb = local_path.stat().st_size // 1024
            lineas.append(f"Archivo local: {local_path.name} ({tamano_kb} KB)")
            # Analizar con la skill real
            try:
                datos = leer_examen(str(local_path))
                if datos.get("error"):
                    # Error tecnico: no lo mostramos en la ficha.
                    # Va al log tecnico para debugging futuro.
                    logger.warning(
                        f"[crear_notas] OCR fallo para {adj.get('nombre')}: "
                        f"{datos['error']}"
                    )
                    lineas.append("")
                    lineas.append(
                        "El analisis automatico (OCR) no pudo procesarlo. "
                        "Ver imagen original adjunta."
                    )
                else:
                    tipo = datos.get("tipo") or "desconocido"
                    lineas.append(f"Tipo detectado: {tipo}")
                    texto = datos.get("texto_ocr", "")
                    if texto:
                        lineas.append("Texto extraido (OCR):")
                        for ln in texto.split("\n"):
                            lineas.append(f"  {ln}")
                        # Si es audiometria, intentar parsear OD/OI
                        if "audio" in (adj.get("nombre") or "").lower():
                            lineas.append("")
                            lineas.append(interpretar_audiometria(datos))
                    else:
                        lineas.append("")
                        lineas.append(
                            "El analisis automatico (OCR) no extrajo texto. "
                            "Ver imagen original adjunta."
                        )
            except Exception as e:  # noqa: BLE001
                # Error tecnico: log + mensaje neutro en la ficha
                logger.warning(
                    f"[crear_notas] Excepcion al analizar {adj.get('nombre')}: {e}"
                )
                lineas.append("")
                lineas.append(
                    "El analisis automatico (OCR) no pudo procesarlo. "
                    "Ver imagen original adjunta."
                )
        else:
            lineas.append("Archivo local: (no se pudo descargar)")
        lineas.append("")
    return "\n".join(lineas)


# ---- Paso 4.2: extraer informacion de la ficha abierta ----

def _wait_visible(driver: WebDriver, selector: str, timeout: int = 10) -> Optional[WebElement]:
    """Espera a que un elemento sea visible. Devuelve None si no aparece.

    Acepta selectores CSS o xpath. Se detecta por el prefijo: si
    empieza con '//' o '(' se trata como xpath; en otro caso CSS.
    """
    if selector.startswith("//") or selector.startswith("("):
        by, val = By.XPATH, selector
    else:
        by, val = By.CSS_SELECTOR, selector
    try:
        wait = WebDriverWait(driver, timeout)
        return wait.until(EC.visibility_of_element_located((by, val)))
    except Exception:  # noqa: BLE001
        return None


def _safe_text(el: Optional[WebElement]) -> str:
    """Devuelve el texto de un WebElement, o string vacio si es None."""
    if el is None:
        return ""
    return el.text.strip()


def extraer_identificacion(driver: WebDriver, logger: logging.Logger) -> dict[str, str]:
    """Extrae la tabla de identificacion del paciente.

    La tabla tiene pares <th>:<td> con campos como RUN, Fecha de nacimiento,
    Direccion, etc. Devuelve un dict {campo: valor}.

    Estrategia de busqueda (orden de fallback):
    1) Cualquier <table> que tenga <th> en <tbody> (estructura del paciente).
    2) Si no, cualquier <table> con <tbody> adentro de un div.side-nav-margin.
    3) Si no, la primera <table.table> de la pagina.

    Cuando un <td> contiene una sub-tabla (caso de Telefono), se
    concatenan los valores en un solo string con " | " como separador.

    Desduplicacion: cuando Rayen lista el mismo telefono bajo varios
    labels ("Telefono", "Tipo otro telefono de contacto", "Telefono
    movil"), el script conserva solo el primero para no triplicar el
    numero.
    """
    logger.info("[crear_notas] Extrayendo tabla de identificacion...")
    out: dict[str, str] = {}
    try:
        table = None

        # Paso 1: tabla con <th> en <tbody> (la del paciente).
        tables_con_th = driver.find_elements(
            By.XPATH,
            "//table[.//tbody/th]",
        )
        if tables_con_th:
            table = tables_con_th[0]
            logger.info(
                f"[crear_notas] Tabla encontrada por <tbody><th> "
                f"({len(tables_con_th)} match)"
            )

        # Paso 2: tabla dentro de div.side-nav-margin.
        if table is None:
            tables_side = driver.find_elements(
                By.XPATH,
                "//div[contains(@class,'side-nav-margin')]//table[.//tbody]",
            )
            if tables_side:
                table = tables_side[0]
                logger.info(
                    f"[crear_notas] Tabla encontrada por side-nav-margin "
                    f"({len(tables_side)} match)"
                )

        # Paso 3: primera tabla.table de la pagina.
        if table is None:
            tables_any = driver.find_elements(By.CSS_SELECTOR, "table.table")
            if tables_any:
                table = tables_any[0]
                logger.info(
                    f"[crear_notas] Tabla encontrada por fallback table.table "
                    f"({len(tables_any)} match)"
                )

        if table is None:
            total_t = len(driver.find_elements(By.CSS_SELECTOR, "table"))
            total_tbody = len(driver.find_elements(By.CSS_SELECTOR, "table tbody"))
            total_th = len(driver.find_elements(By.CSS_SELECTOR, "table th"))
            logger.warning(
                f"[crear_notas] No se encontro tabla. DOM tiene: "
                f"tables={total_t}, tbodies={total_tbody}, ths={total_th}"
            )
            return out

        rows = table.find_elements(By.CSS_SELECTOR, "tbody tr")
        pares: list[tuple[str, str]] = []
        for r in rows:
            th_elements = r.find_elements(By.CSS_SELECTOR, "th")
            if not th_elements:
                continue
            th_text = _safe_text(th_elements[0])
            tds = r.find_elements(By.CSS_SELECTOR, "td")
            if not th_text or not tds:
                continue
            # Si el td es una sub-tabla (caso de Telefono), concatenar
            # los valores de la sub-tabla en un solo string.
            subtable = tds[0].find_elements(By.CSS_SELECTOR, "table")
            if subtable:
                celdas_sub = subtable[0].find_elements(By.CSS_SELECTOR, "td")
                valores = []
                for celda in celdas_sub:
                    txt = _safe_text(celda)
                    if txt:
                        valores.append(txt)
                td_text = " | ".join(valores) if valores else _safe_text(tds[0])
            else:
                td_text = _safe_text(tds[0])
            if td_text:
                pares.append((th_text, td_text))

        # Desduplicar telefonos consecutivos con el mismo valor.
        patron_telefono = re.compile(
            r"tel[eé]fono|tel[eé]fonos|movil|m[oó]vil|contacto",
            re.IGNORECASE,
        )
        filtrados: list[tuple[str, str]] = []
        prev_telefono_value: str | None = None
        for label, valor in pares:
            es_tel = bool(patron_telefono.search(label))
            if (
                es_tel
                and prev_telefono_value is not None
                and valor.strip() == prev_telefono_value
            ):
                continue
            filtrados.append((label, valor))
            if es_tel:
                prev_telefono_value = valor.strip()
            else:
                prev_telefono_value = None

        for label, valor in filtrados:
            out[label] = valor
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo identificacion: {e}")
    logger.info(f"[crear_notas] Identificacion: {len(out)} campos")
    return out


def extraer_historial(
    driver: WebDriver, logger: logging.Logger
) -> str:
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
            f"[crear_notas] historial JS retorno: len={len(result)} "
            f"preview={result[:200]!r}"
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
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo historial: {e}")
        return ""


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
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", li
        )
        time.sleep(0.3)
        try:
            li.click()
        except Exception:  # noqa: BLE001
            driver.execute_script("arguments[0].click();", li)
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "li#anamnesis")
            )
        )
        logger.info(
            "[crear_notas] Click OK en 'Atencion actual', li#anamnesis presente"
        )
        return True
    except TimeoutException:
        logger.warning(
            "[crear_notas] Panel Evaluacion no cargo en 8s. La anamnesis "
            "del paciente esta disponible en Rayen para revision manual."
        )
        return False
    except Exception as e:  # noqa: BLE001
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
            logger.warning(
                "[crear_notas] Motivo: li#anamnesis no existe en el DOM"
            )
            return ""
        if texto == "__NO_CANDIDATOS__":
            logger.warning(
                "[crear_notas] Motivo: li#anamnesis existe pero no tiene "
                ".textoverflow-container fuera de .collapse-text-sub"
            )
            return ""
        texto = texto.strip()
        logger.info(
            f"[crear_notas] Motivo de consulta extraido: {len(texto)} chars"
        )
        return texto
    except Exception as e:  # noqa: BLE001
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
        anamnesis_li = driver.find_element(
            By.CSS_SELECTOR, "li#anamnesis"
        )
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
        logger.info(
            f"[crear_notas] Diag anamnesis ANTES de ver_mas: {diag_inicial}"
        )
        # Intentar expandir el "...ver mas" si existe, para asegurar que el
        # texto este visible y copiable
        try:
            ver_mas = anamnesis_li.find_element(
                By.CSS_SELECTOR, ".textoverflow-button"
            )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});", ver_mas
            )
            time.sleep(0.3)
            try:
                ver_mas.click()
            except Exception:  # noqa: BLE001
                driver.execute_script("arguments[0].click();", ver_mas)
            time.sleep(0.5)
        except Exception:  # noqa: BLE001
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
        logger.info(
            f"[crear_notas] Anamnesis extraida: {len((contenido or '').strip())} chars"
        )
        contenido = (contenido or "").strip()
        logger.info(f"[crear_notas] Anamnesis extraida: {len(contenido)} chars")
        return contenido
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo anamnesis: {e}")
        return ""


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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
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
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo profesionales: {e}")
        return []


def extraer_recetas(driver: WebDriver, logger: logging.Logger) -> list[str]:
    """Extrae las recetas (Plan → Recetas) que Yadira dejo escritas.

    DOM (validado 2026-08-26 con Karina Ximena Tapia Herrera, G2):
      - Panel: div#right-side-attention
      - Top-level section Recetas: <li.expand-icons-sm> con
        .expandable-title == "Recetas"
      - Cada prescripcion dentro: <li.list-group-item> que contiene un
        <button id="prescription-edit-XXX"> (mas prescription-delete- y
        prescription-print-). El header trae:
          * .pl-0.col-md-12 con el tipo (Cronica / Aguda)
          * .pl-0.collapse-text-sub.col-md-12 con "Vigencia <fecha>"
      - Lista de farmacos: dentro del bloque colapsado
        div.collapse-text.collapse siguiente al header. Cada farmaco es
        un <li.px-0.border-0.mb-2.list-group-item> con:
          * <div>NOMBRE</div>
          * <div class="collapse-text-sub">POSOLOGIA</div>

    Devuelve una lista de strings (uno por prescripcion), cada uno con
    varias lineas:
        - [Cronica] Vigencia: 25 ago. 2027
        \t- Sertralina 50 mg comprimidos (2 Comprimidos cada 24 Horas por 90 Dias)
        \t- Quetiapina 100 mg comprimidos (2 Comprimidos cada 24 Horas por 90 Dias)
    """
    logger.info("[crear_notas] Extrayendo recetas (Plan -> Recetas)...")
    js = r"""
    const out = [];
    const plan = document.querySelector('div#right-side-attention');
    if (!plan) return out;
    // Top-level Recetas section: <li.expand-icons-sm> con title Recetas
    const top = plan.querySelectorAll('ul.list-group > li.expand-icons-sm');
    let recetasLi = null;
    top.forEach(li => {
        const t = li.querySelector(':scope > .container > .row .expandable-title');
        if (t && (t.textContent || '').trim() === 'Recetas') recetasLi = li;
    });
    if (!recetasLi) return out;
    // Cada prescripcion: li que contiene un button con id prescription-edit-XXX
    const editBtns = recetasLi.querySelectorAll('button[id^="prescription-edit-"]');
    editBtns.forEach(btn => {
        const prescLi = btn.closest('li.list-group-item');
        if (!prescLi) return;
        // Tipo (Cronica/Aguda): primer .pl-0.col-md-12 directo bajo col-sm-7
        const typeCell = prescLi.querySelector(
            '.col-sm-7 .pl-0.col-md-12:not(.collapse-text-sub)'
        );
        const tipo = typeCell ? (typeCell.textContent || '').trim() : '';
        // Vigencia: .pl-0.collapse-text-sub.col-md-12
        const vigCell = prescLi.querySelector(
            '.col-sm-7 .pl-0.collapse-text-sub.col-md-12'
        );
        let vigencia = '';
        if (vigCell) {
            vigencia = (vigCell.textContent || '')
                .replace(/^\s*Vigencia\s*/i, '')
                .trim();
        }
        // Lista de farmacos: li.px-0.border-0.mb-2.list-group-item dentro
        // del bloque colapsado siguiente al header de la prescripcion
        const drugLis = prescLi.querySelectorAll(
            'li.px-0.border-0.mb-2.list-group-item'
        );
        const drugLines = [];
        drugLis.forEach(dli => {
            const divs = dli.querySelectorAll(':scope > div');
            // Primer div = nombre, segundo = posologia
            const nombre = divs[0] ? (divs[0].textContent || '').trim() : '';
            const posologia = divs[1] ? (divs[1].textContent || '').trim() : '';
            if (nombre) {
                if (posologia) {
                    drugLines.push(`\t- ${nombre} (${posologia})`);
                } else {
                    drugLines.push(`\t- ${nombre}`);
                }
            }
        });
        const headerParts = [];
        if (tipo) headerParts.push(`[${tipo}]`);
        if (vigencia) headerParts.push(`Vigencia: ${vigencia}`);
        const header = headerParts.length
            ? `- ${headerParts.join(' ')}`
            : '- (prescripcion sin tipo/vigencia)';
        out.push([header, ...drugLines].join('\n'));
    });
    return out;
    """
    try:
        result = driver.execute_script(js)
        recetas = [r for r in (result or []) if r]
        logger.info(
            f"[crear_notas] Recetas extraidas: {len(recetas)} prescripcion(es)"
        )
        return recetas
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo recetas: {e}")
        return []


def extraer_laboratorio(
    driver: WebDriver, logger: logging.Logger
) -> list[str]:
    """Extrae la orden de examen de laboratorio (Plan -> Laboratorio).

    DOM (validado 2026-08-26 con Karina Ximena Tapia Herrera, G2):
      - Panel: div#right-side-attention
      - Top-level "Orden de examen": <li.expand-icons-sm> con
        .expandable-title == "Orden de examen"
      - Subseccion "Laboratorio": <div.container.mb-0.pl-0> con texto
        "Laboratorio"
      - Cada orden de lab: <li id="laboratory-item-XXXXX"> con un
        <div.mb-3> adentro, y cada examen es un <div> directo hijo
        con el nombre del examen

    Devuelve una lista de strings (uno por orden de laboratorio):
        - Orden lab #1:
        \t- Creatinina en sangre
        \t- Electrolitos plasmaticos
        \t- Microalbuminuria aislada
        ...
    Si no hay subseccion Laboratorio, devuelve [].
    """
    logger.info("[crear_notas] Extrayendo laboratorio (Plan -> Laboratorio)...")
    js = r"""
    const out = [];
    const plan = document.querySelector('div#right-side-attention');
    if (!plan) return out;
    // Top-level "Orden de examen"
    const top = plan.querySelectorAll('ul.list-group > li.expand-icons-sm');
    let ordenLi = null;
    top.forEach(li => {
        const t = li.querySelector(':scope > .container > .row .expandable-title');
        if (t && (t.textContent || '').trim() === 'Orden de examen') ordenLi = li;
    });
    if (!ordenLi) return out;
    // Verificar que exista la subseccion "Laboratorio"
    const labTitle = Array.from(
        ordenLi.querySelectorAll('.expand-wrapper-title-s .container.mb-0.pl-0')
    ).find(d => (d.textContent || '').trim() === 'Laboratorio');
    if (!labTitle) return out;
    // Cada orden de lab: li#laboratory-item-XXXXX
    const labOrders = ordenLi.querySelectorAll('li[id^="laboratory-item-"]');
    labOrders.forEach((orderLi, idx) => {
        const examDivs = orderLi.querySelectorAll(':scope > .row > .col-sm-7 > .mb-3 > div');
        const lines = [`- Orden lab #${idx + 1}:`];
        examDivs.forEach(d => {
            const name = (d.textContent || '').trim();
            if (name) lines.push(`\t- ${name}`);
        });
        out.push(lines.join('\n'));
    });
    return out;
    """
    try:
        result = driver.execute_script(js)
        laboratorio = [l for l in (result or []) if l]
        logger.info(
            f"[crear_notas] Laboratorio extraido: "
            f"{len(laboratorio)} orden(es)"
        )
        return laboratorio
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo laboratorio: {e}")
        return []


# ---- Regla Yadira 2026-08-26: tipo=Recetas -> solo la receta mas reciente ----
# Cuando el tipo de atencion es "Recetas", la ficha rellenada por Mortadelo
# debe incluir UNICAMENTE la prescripcion con la Vigencia mas reciente.
# Esto evita que se acumulen en el bloque Doctora sugerencias sobre recetas
# que ya fueron reemplazadas por una nueva.

_MONTHS_ES: dict[str, int] = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dic": 12,
}

_VIGENCIA_RE = re.compile(
    r"Vigencia\s*:?\s*(\d{1,2})\s+([a-zA-ZáéíóúÁÉÍÓÚ]{3,4})\.?\s+(\d{4})",
    re.IGNORECASE,
)


def _parsear_vigencia(primera_linea: str) -> _date | None:
    """Parsea 'Vigencia: 25 ago. 2027' a date. None si no matchea."""
    m = _VIGENCIA_RE.search(primera_linea or "")
    if not m:
        return None
    day_s, mes_s, year_s = m.groups()
    mes_num = _MONTHS_ES.get(mes_s.lower()[:4]) or _MONTHS_ES.get(
        mes_s.lower()[:3]
    )
    if not mes_num:
        return None
    try:
        return _date(int(year_s), mes_num, int(day_s))
    except ValueError:
        return None


def _filtrar_receta_mas_reciente(recetas: list[str]) -> list[str]:
    """Devuelve la receta con la Vigencia mas reciente.

    Si solo hay 0 o 1 receta, devuelve la lista tal cual. Si ninguna fecha
    se logra parsear, devuelve la ULTIMA receta (el orden de extraccion
    de Rayen suele ir de mas viejo a mas nuevo, asi que la ultima suele
    ser la mas reciente). Si no, ordena por fecha desc y devuelve [0].
    """
    if len(recetas) <= 1:
        return list(recetas)
    parsed: list[tuple[int, _date]] = []
    for i, r in enumerate(recetas):
        primera = r.split("\n", 1)[0] if r else ""
        d = _parsear_vigencia(primera)
        if d is not None:
            parsed.append((i, d))
    if not parsed:
        return [recetas[-1]]
    parsed.sort(key=lambda x: x[1], reverse=True)
    return [recetas[parsed[0][0]]]


def _tipo_atencion_es_recetas(tipo: str | None) -> bool:
    """True si el tipo_atencion matchea 'Recetas' (case/accent insensitive)."""
    if not tipo:
        return False
    t = " ".join(tipo.strip().lower().split())
    t = "".join(
        c for c in unicodedata.normalize("NFD", t)
        if unicodedata.category(c) != "Mn"
    )
    return t == "recetas"


def extraer_pautas(driver: WebDriver, logger: logging.Logger) -> list[str]:
    """Extrae las pautas (formularios/evaluaciones) aplicadas en la atencion."""
    logger.info("[crear_notas] Extrayendo pautas...")
    js = r"""
    const items = document.querySelectorAll('li[id^="pauta-"]');
    return Array.from(items).map(li => {
        const nombreEl = li.querySelector('.w-75');
        const fechaEl = li.querySelector('.date-display');
        const nombre = nombreEl ? (nombreEl.textContent || '').trim() : '';
        const fecha = fechaEl ? (fechaEl.textContent || '').trim() : '';
        if (nombre && fecha) return `- ${nombre} (${fecha})`;
        if (nombre) return `- ${nombre}`;
        return '';
    }).filter(x => x);
    """
    try:
        result = driver.execute_script(js)
        pautas = [p for p in (result or []) if p]
        logger.info(f"[crear_notas] Pautas extraidas: {len(pautas)}")
        return pautas
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo pautas: {e}")
        return []


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
    except Exception:  # noqa: BLE001
        return False


def _popover_estratificacion_visible(driver: WebDriver) -> bool:
    """True si el popover de estratificacion (.stratification-card) esta visible."""
    try:
        card = driver.find_element(By.CSS_SELECTOR, _ESTRAT_CARD_SELECTOR)
        return card.is_displayed()
    except Exception:  # noqa: BLE001
        return False


def _abrir_popover_estratificacion(
    driver: WebDriver, logger: logging.Logger
) -> bool:
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
            By.CSS_SELECTOR,
            "button.bg-transparent[aria-haspopup='true'] span.badge.badge-pill"
        )
        logger.info(
            f"[crear_notas] Badge encontrado: texto={(badge.text or '').strip()!r}"
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", badge
        )
        time.sleep(0.3)
        try:
            badge.click()
        except Exception:  # noqa: BLE001
            driver.execute_script("arguments[0].click();", badge)
        # Esperar a que el popover sea visible
        try:
            WebDriverWait(driver, 5).until(
                lambda d: any(
                    c.is_displayed()
                    for c in d.find_elements(
                        By.CSS_SELECTOR, _ESTRAT_CARD_SELECTOR
                    )
                )
            )
        except TimeoutException:
            logger.warning(
                "[crear_notas] Popover de estrat. no aparecio tras click"
            )
            return False
        time.sleep(0.3)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[crear_notas] No se pudo abrir popover de estrat.: {e}"
        )
        return False


def _abrir_modal_estratificacion(
    driver: WebDriver, logger: logging.Logger
) -> bool:
    """Hace click en 'Ver todos los diagnosticos activos' para abrir el modal."""
    try:
        trigger = driver.find_element(
            By.CSS_SELECTOR, _ESTRAT_MODAL_TRIGGER_SELECTOR
        )
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", trigger
        )
        time.sleep(0.3)
        try:
            trigger.click()
        except Exception:  # noqa: BLE001
            driver.execute_script("arguments[0].click();", trigger)
        try:
            WebDriverWait(driver, 5).until(
                lambda d: any(
                    m.is_displayed()
                    for m in d.find_elements(
                        By.CSS_SELECTOR, _ESTRAT_MODAL_SELECTOR
                    )
                )
            )
        except TimeoutException:
            logger.warning(
                "[crear_notas] Modal de estrat. no aparecio tras click"
            )
            return False
        time.sleep(0.5)
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[crear_notas] No se pudo abrir modal de estrat.: {e}"
        )
        return False


def _cerrar_modal_estratificacion(
    driver: WebDriver, logger: logging.Logger
) -> None:
    """Cierra el modal de diagnosticos activos. Best-effort."""
    for sel in _ESTRAT_MODAL_CLOSE_SELECTORS:
        try:
            btns = driver.find_elements(By.CSS_SELECTOR, sel)
        except Exception:  # noqa: BLE001
            continue
        for btn in btns:
            try:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(0.3)
                    return
            except Exception:  # noqa: BLE001
                continue
    try:
        driver.execute_script(
            "document.querySelector('.modal-backdrop')?.click();"
        )
    except Exception:  # noqa: BLE001
        pass
    try:
        from selenium.webdriver.common.keys import Keys

        driver.find_element(By.CSS_SELECTOR, "body").send_keys(Keys.ESCAPE)
    except Exception:  # noqa: BLE001
        pass


def _cerrar_popover_estratificacion(
    driver: WebDriver, logger: logging.Logger
) -> None:
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
                    "button.bg-transparent[aria-haspopup='true']"
                    " span.badge.badge-pill"
                )
                driver.execute_script("arguments[0].click();", badge)
                time.sleep(0.3)
            except Exception:  # noqa: BLE001
                pass
        # Fallback: click en el body + ESC
        try:
            driver.execute_script(
                "document.body.click();"
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            from selenium.webdriver.common.keys import Keys

            driver.find_element(
                By.CSS_SELECTOR, "body"
            ).send_keys(Keys.ESCAPE)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.3)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[crear_notas] No se pudo cerrar popover de estrat.: {e}"
        )


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


def extraer_estratificacion_ecicep(
    driver: WebDriver, logger: logging.Logger
) -> dict[str, Any]:
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
    except Exception as e:  # noqa: BLE001
        logger.warning(
            f"[crear_notas] Error leyendo card de estratificacion: {e}"
        )
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
        logger.info(
            "[crear_notas] Abriendo popover de estratificacion (click badge)..."
        )
        if not _abrir_popover_estratificacion(driver, logger):
            logger.warning(
                "[crear_notas] No se pudo abrir el popover. "
                "Solo se extraera badge + fecha_inicio."
            )
            return out

    if not _modal_estratificacion_visible(driver):
        logger.info(
            "[crear_notas] Abriendo modal de diagnosticos activos para "
            "estratificacion..."
        )
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
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error leyendo modal de estrat.: {e}")

    _cerrar_modal_estratificacion(driver, logger)
    _cerrar_popover_estratificacion(driver, logger)

    logger.info(
        f"[crear_notas] Estrat. ECICEP: grupo={out['grupo']} "
        f"agudos={len(out['agudos'])} cronicos={len(out['cronicos'])}"
    )
    return out


def extraer_otros_items_atencion(
    driver: WebDriver, logger: logging.Logger
) -> dict[str, str]:
    """Extrae cualquier item de la atencion que no sea anamnesis, diagnosticos,
    actividades, profesionales o pautas (placeholders para futuras secciones).
    """
    logger.info("[crear_notas] Extrayendo otros items de la atencion...")
    out: dict[str, str] = {}
    contenedor = _wait_visible(
        driver, "div#left-side-attention, div.side-card .attention-scrollable", timeout=8
    )
    if contenedor is None:
        return out
    try:
        ids_excluidos = (
            "anamnesis", "diagnose-", "activity-",
            "multiProfessional-", "pauta-",
        )
        sel = "li.list-group-item[id]"
        for pref in ids_excluidos:
            sel += f":not([id='{pref}'])" if pref == "anamnesis" else f":not([id^='{pref}'])"
        items = contenedor.find_elements(By.CSS_SELECTOR, sel)
        for item in items:
            titulo_el = None
            try:
                titulo_el = item.find_element(By.CSS_SELECTOR, ".expandable-title")
            except Exception:  # noqa: BLE001
                pass
            titulo = _safe_text(titulo_el) or item.get_attribute("id") or "(seccion)"
            contenido_el = None
            try:
                contenido_el = item.find_element(
                    By.CSS_SELECTOR, ".collapse-text"
                )
            except Exception:  # noqa: BLE001
                pass
            contenido = _safe_text(contenido_el)
            if contenido:
                out[titulo] = contenido
        return out
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[crear_notas] Error extrayendo otros items: {e}")
        return out


# ---- Paso 4.3: guardar nota clinica en archivo .txt ----

def _safe_filename(s: str) -> str:
    """Convierte un nombre a filename seguro (sin caracteres raros)."""
    s = re.sub(r"[^\w\s\-]+", "", s, flags=re.UNICODE)
    s = re.sub(r"\s+", "_", s.strip())
    return s


def guardar_nota_clinica(
    paciente: PacienteObjetivo,
    identificacion: dict[str, str],
    historial: str,
    anamnesis: str,
    diagnosticos: list[str],
    actividades: list[str],
    profesionales: list[str],
    pautas: list[str],
    examenes: str = "",
    otros_items: dict[str, str] = None,
    estratificacion: dict[str, Any] | None = None,
    motivo_consulta: str = "",
    recetas: list[str] | None = None,
    laboratorio: list[str] | None = None,
    notas_dir: Path = None,
    panel_cargo: bool = True,
) -> Optional[Path]:
    """Guarda la nota clinica extraida en un .md en armonia con manuales_md.

    Sesion 2026-09-16: cambio de .txt con marcadores '=== INICIO/FIN ==='
    a markdown con frontmatter YAML + headers (##). Mismo formato que
    `manuales_md/<basename>/<basename>.md`. Esto permite que Yadira, el
    LLM y los scripts que parsean manuales trabajen sobre una sola
    estructura.

    Sesion 2026-09-16 14:14 (regla Yadira): el script SIEMPRE escribe
    el archivo (sobrescribe si existe). El script NO depende de la
    existencia de un archivo previo para arrancar ni para decidir que
    hacer; cada corrida arranca fresca desde Rayen. Si la extraccion
    falla (anamnesis vacia, panel no cargo), ValueError y el archivo
    NO se escribe en absoluto (eso lo cubre el try/except del pipeline
    y el test de rechazo correspondiente).

    Estructura del .md generado:
        ---
        <frontmatter YAML>
        ---
        # Nota clinica - <paciente>
        (flag si panel no cargo)
        ## Identificacion
        ## Historial de atenciones (ultimos 6 meses)
        ## Nota clinica de Yadira
        ## Diagnosticos
        ## Estratificacion ECICEP (solo si hay grupo)
        ## Actividades
        ## Profesionales
        ## Plan - Recetas
        ## Plan - Laboratorio

    La seccion ESTRATIFICACION ECICEP solo aparece si el paciente esta
    estratificado (la extraccion devolvio un grupo). Va entre
    DIAGNOSTICOS y ACTIVIDADES, porque es informacion del sistema
    (no de la atencion actual) que sirve para el ECICEP.

    El motivo de consulta (si lo hay) va DENTRO de la seccion
    "Nota clinica de Yadira" como blockquote en la primera linea.

    El historial de atenciones se filtra a las entradas de los ultimos
    6 meses respecto a paciente.fecha.

    Raises:
        ValueError: si `anamnesis` esta vacia. Regla dura de Yadira
            (sesion 2026-09-16): Rayen SIEMPRE tiene la anamnesis
            escrita por la doctora al abrir la ficha. Si la extraccion
            no la encontro, es un bug del extractor y el archivo NO se
            debe escribir (nota sin anamnesis no sirve). El pipeline
            caller atrapa la excepcion y marca al paciente como error.
    """
    if otros_items is None:
        otros_items = {}
    if recetas is None:
        recetas = []
    if laboratorio is None:
        laboratorio = []
    _log = logging.getLogger("crear_notas_clinicas")
    if not (anamnesis or "").strip():
        _log.error(
            f"[crear_notas] {paciente.nombre}: anamnesis vacia. "
            f"Rayen SIEMPRE tiene la anamnesis escrita por Yadira al "
            f"abrir la ficha (regla dura). Extraccion fallo: NO se "
            f"escribe la nota. panel_cargo={panel_cargo}."
        )
        raise ValueError(
            f"anamnesis vacia para {paciente.nombre}: la extraccion "
            f"fallo (panel_cargo={panel_cargo}). Ver logs de "
            f"`extraer_anamnesis()` y reintentar."
        )
    historial = filtrar_historial_ultimos_6_meses(
        historial, paciente.fecha, logger=_log
    )
    nombre_archivo = (
        f"{_safe_filename(paciente.nombre)}_{paciente.fecha}.md"
    )
    out_path = notas_dir / nombre_archivo
    # Sesion 2026-09-16 14:14 (regla Yadira): el script NO depende de
    # la existencia de un archivo anterior. Si el archivo ya existe
    # (corrida previa que escribio la misma paciente/fecha), SE
    # SOBREESCRIBE con la extraccion nueva. La diferencia con versiones
    # anteriores: esto es overwrite NATURAL de una nueva corrida, NO
    # una estrategia "leer archivo viejo para mejorar". Si la extraccion
    # falla, NO se reescribe (eso lo maneja el try/except del pipeline).
    notas_dir.mkdir(parents=True, exist_ok=True)

    # ---- Frontmatter YAML ----
    md = ["---"]
    md.append(f'paciente: "{paciente.nombre}"')
    md.append(f'title: "Nota clinica - {paciente.nombre}"')
    md.append(f'fecha_atencion: "{paciente.fecha}"')
    md.append(f'tipo_atencion: "{paciente.tipo_atencion}"')
    if paciente.nombre_rayen and paciente.nombre_rayen != paciente.nombre:
        md.append(f'paciente_rayen: "{paciente.nombre_rayen}"')
    md.append('fuente: "Rayen APS - CESFAM Raul Cuevas, San Bernardo"')
    md.append('source_url: "https://clinico.rayenaps.cl/"')
    md.append(f'fecha_extraccion: "{_now_iso()}"')
    md.append(f'panel_cargo: "{str(panel_cargo).lower()}"')
    md.append("---")
    md.append("")

    # ---- Titulo ----
    md.append(f"# Nota clinica - {paciente.nombre}")
    md.append("")

    # ---- Flag de revision si aplica ----
    if not panel_cargo:
        md.append(
            "> ⚠️ **ATENCION: panel del paciente NO CARGO en Rayen.**"
        )
        md.append(
            "> La nota tiene placeholders. Revisar manualmente en Rayen."
        )
        md.append("")

    # ---- Secciones ----
    md.append("## Identificacion")
    md.append("")
    if identificacion:
        for k, v in identificacion.items():
            md.append(f"- **{k}:** {v}")
    else:
        md.append("_(no se pudo extraer la tabla de identificacion)_")
    md.append("")

    md.append("## Historial de atenciones (ultimos 6 meses)")
    md.append("")
    md.append(historial or "_(no se pudo extraer el historial)_")
    md.append("")

    md.append("## Nota clinica de Yadira")
    md.append("")
    # Sesion 2026-09-16 (corregido 13:42 tras feedback de Yadira): el
    # bloque Yadira contiene la ANAMNESIS CRUDA que Yadira lleno en
    # Rayen al abrir la ficha. Es el INSUMO PRINCIPAL del flujo:
    # `completar_yadira.py` lee este bloque, lo pasa al LLM junto con
    # los demas bloques estructurados + manuales + conocimiento medico,
    # y el LLM lo enriquece en una version final que Yadira revisa.
    # El resultado del enriquecimiento se guarda en
    # `notas_clinicas_completadas/<paciente>_<fecha>.md`.
    if motivo_consulta:
        md.append(f"> **Motivo de atencion:** {motivo_consulta}")
        md.append("")
    if anamnesis and anamnesis.strip():
        md.append(anamnesis.strip())
    else:
        # Si llegamos aca, el ValueError de arriba deberia haber
        # detenido la escritura. Esto es solo defensa en profundidad.
        md.append("_(sin anamnesis — error de extraccion)_")
    md.append("")

    md.append("## Diagnosticos")
    md.append("")
    if diagnosticos:
        for d in diagnosticos:
            md.append(f"- {d.lstrip('- ')}")  # evitar "- - ..."
    else:
        md.append("_(sin diagnosticos)_")
    md.append("")

    estrat_texto = formatear_estratificacion(estratificacion)
    if estrat_texto:
        md.append("## Estratificacion ECICEP")
        md.append("")
        md.append(estrat_texto)
        md.append("")

    md.append("## Actividades")
    md.append("")
    if actividades:
        for a in actividades:
            md.append(f"- {a}")
    else:
        md.append("_(sin actividades)_")
    md.append("")

    md.append("## Profesionales")
    md.append("")
    if profesionales:
        for p in profesionales:
            md.append(f"- {p}")
    else:
        md.append("_(sin profesionales)_")
    md.append("")

    md.append("## Plan - Recetas")
    md.append("")
    if recetas:
        for r in recetas:
            for i, sub in enumerate(r.split("\n")):
                if i == 0:
                    md.append(f"- {sub}")
                else:
                    md.append(f"  - {sub}")
    else:
        md.append("_(sin recetas)_")
    md.append("")

    md.append("## Plan - Laboratorio")
    md.append("")
    if laboratorio:
        for lab in laboratorio:
            for i, sub in enumerate(lab.split("\n")):
                if i == 0:
                    md.append(f"- {sub}")
                else:
                    md.append(f"  - {sub}")
    else:
        md.append("_(sin ordenes de laboratorio)_")
    md.append("")

    # SCOPE 2026-08-26: bloques quitados (fuera de scope):
    # - PAUTAS
    # - EXAMENES ADJUNTOS
    # - OTROS ITEMS DE LA ATENCION
    # - Plan -> Imagenologia
    # - Plan -> Interconsulta
    out_path.write_text("\n".join(md), encoding="utf-8")
    logger = logging.getLogger("crear_notas_clinicas")
    logger.info(f"[crear_notas] Nota clinica guardada en: {out_path}")
    return out_path


def _now_iso() -> str:
    """Helper: timestamp ISO 8601 al segundo. Usado para el frontmatter."""
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _rellenar_bloque_en_nota(
    nota_path: Path, bloque: str, contenido_nuevo
) -> None:
    """Sobrescribe el contenido del bloque dado en el archivo de la nota.

    Sesion 2026-09-16 14:14 (regla Yadira): si validar_nota_clinica
    detecta un bloque faltante y re_extraer_bloque() trajo contenido,
    esta funcion actualiza SOLO ese bloque, manteniendo el resto del
    archivo intacto. Es el "fix" parcial post-write.

    Args:
        nota_path: path al .md a actualizar.
        bloque: nombre del bloque (header `## <nombre>`).
        contenido_nuevo: contenido nuevo del bloque. Puede ser:
            - str (para bloques de texto como anamnesis, historial,
              motivo consulta)
            - list[str] (para bloques de bullets como diagnosticos,
              actividades, recetas)
            - dict[str, str] (para bloques clave-valor como
              identificacion)
        Se serializa al formato markdown apropiado.
    """
    contenido = nota_path.read_text(encoding="utf-8")
    lineas = contenido.splitlines()
    out: list[str] = []
    en_bloque = False
    bloque_reemplazado = False

    # Serializar contenido_nuevo al formato markdown apropiado.
    lineas_nuevas: list[str] = []
    if isinstance(contenido_nuevo, str):
        if contenido_nuevo.strip():
            lineas_nuevas.append(contenido_nuevo.strip())
            lineas_nuevas.append("")
    elif isinstance(contenido_nuevo, list):
        for item in contenido_nuevo:
            lineas_nuevas.append(f"- {item}")
        if lineas_nuevas:
            lineas_nuevas.append("")
    elif isinstance(contenido_nuevo, dict):
        for k, v in contenido_nuevo.items():
            lineas_nuevas.append(f"- **{k}:** {v}")
        if lineas_nuevas:
            lineas_nuevas.append("")

    for i, line in enumerate(lineas):
        if line.startswith(f"## {bloque}"):
            en_bloque = True
            out.append(line)
            out.append("")
            out.extend(lineas_nuevas)
            bloque_reemplazado = True
            # Saltar hasta el siguiente header.
            j = i + 1
            while j < len(lineas) and not lineas[j].startswith("## "):
                j += 1
            continue
        if en_bloque:
            if line.startswith("## "):
                en_bloque = False
                out.append(line)
            # Si estamos en el bloque siendo reemplazado, saltamos.
            continue
        out.append(line)

    if not bloque_reemplazado:
        return  # bloque no encontrado, no hacer nada

    nota_path.write_text("\n".join(out), encoding="utf-8")

def _reintentar_extraccion_anamnesis(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
    click_ok: bool,
    identificacion: dict[str, str],
    historial: str,
    diagnosticos: list[str],
    actividades: list[str],
    profesionales: list[str],
    recetas: list[str],
    laboratorio: list[str],
    examenes: str,
    otros_items: dict[str, str],
    estratificacion: dict[str, Any] | None,
    motivo_consulta: str,
    pautas: list[str],
    notas_dir: Path,
    max_intentos: int = 3,
) -> Path | None:
    """Sesion 2026-09-16 14:50 (regla Yadira): si la extraccion de
    anamnesis falla, NO escribir marker. El script debe REINTENTAR
    la extraccion (re-click en 'Atencion actual' + re-extraer
    anamnesis) hasta N veces. Solo si agota todos los reintentos
    retorna None (Yadira re-corre cuando Rayen este estable).

    Args:
        click_ok: si el click en 'Atencion actual' fue exitoso
            originalmente. Si False, no se puede re-clickear; retorna
            None inmediatamente.
        max_intentos: numero maximo de reintentos (default 3).

    Returns:
        Path al .md escrito si algun reintento tuvo exito, o None si
        agoto todos los reintentos sin exito.
    """
    if not click_ok:
        logger.warning(
            f"[crear_notas] {paciente.nombre}: panel NO cargo "
            f"(click_ok=False). No se puede reintentar la extraccion "
            f"desde aqui. Yadira debera re-correr con Rayen estable."
        )
        return None

    for intento in range(1, max_intentos + 1):
        logger.info(
            f"[crear_notas] {paciente.nombre}: reintento "
            f"{intento}/{max_intentos} de extraccion de anamnesis "
            f"(re-click 'Atencion actual')..."
        )
        try:
            # Re-click en "Atencion actual" para forzar recargar el
            # panel de Evaluacion. Si ya esta clickeado, no-op.
            click_atencion_actual(driver, logger)
            # Re-extraer anamnesis con el panel ya (re)cargado.
            anamnesis_nueva = extraer_anamnesis(driver, logger)
            if anamnesis_nueva and anamnesis_nueva.strip():
                # Reintento exitoso. Escribir nota con la nueva
                # anamnesis.
                logger.info(
                    f"[crear_notas] {paciente.nombre}: reintento "
                    f"{intento} exitoso ({len(anamnesis_nueva)} chars)."
                )
                return guardar_nota_clinica(
                    paciente, identificacion, historial,
                    anamnesis_nueva, diagnosticos, actividades,
                    profesionales, pautas, examenes, otros_items,
                    estratificacion, motivo_consulta, recetas,
                    laboratorio, notas_dir,
                    panel_cargo=paciente.panel_cargo,
                )
        except Exception as re_err:
            logger.warning(
                f"[crear_notas] {paciente.nombre}: reintento "
                f"{intento} lanzo excepcion: {type(re_err).__name__}: "
                f"{re_err!r}"
            )

    logger.error(
        f"[crear_notas] {paciente.nombre}: extraccion fallo despues "
        f"de {max_intentos} reintentos. No se escribe archivo. "
        f"Yadira debera re-correr `crear_notas_clinicas` cuando "
        f"Rayen este estable."
    )
    return None


def validar_nota_clinica(nota_path: Path) -> list[str]:
    """Lee un .md de nota clinica y retorna la lista de bloques que estan
    vacios (es decir, bloques que requieren re-fetch).

    Sesion 2026-09-16 14:14 (regla Yadira): despues de escribir la nota,
    el script valida que todos los bloques tengan contenido. Si falta
    alguno, va a buscarlo a Rayen y sobrescribe el archivo con el bloque
    completado.

    Bloques requeridos (si el extractor fallo, son huecos a re-fetch):
    - Identificacion
    - Historial de atenciones
    - Nota clinica de Yadira (anamnesis cruda)
    - Diagnosticos
    - Actividades
    - Profesionales

    Bloques opcionales (pueden estar vacios legitimamente):
    - Plan - Recetas (consultas sin prescripcion)
    - Plan - Laboratorio (consultas sin ordenes)
    - Estratificacion ECICEP (solo si paciente estratificado)

    Returns:
        Lista de nombres de bloques vacios (sin contenido).
        Lista vacia = OK.
    """
    contenido = nota_path.read_text(encoding="utf-8")
    faltantes: list[str] = []

    # Cada bloque: delimitar por "## " header y chequear contenido hasta
    # el siguiente "## " (o fin de archivo).
    bloques = {}
    nombre_actual = None
    contenido_actual: list[str] = []
    en_frontmatter = True

    for line in contenido.splitlines():
        if en_frontmatter:
            if line.strip() == "---":
                en_frontmatter = False
            continue
        if line.startswith("## "):
            if nombre_actual is not None:
                bloques[nombre_actual] = "\n".join(contenido_actual).strip()
            nombre_actual = line[3:].strip()
            contenido_actual = []
        else:
            contenido_actual.append(line)
    if nombre_actual is not None:
        bloques[nombre_actual] = "\n".join(contenido_actual).strip()

    # Chequear bloques requeridos (los que DEBEN tener contenido si se
    # pudo extraer; recetas/laboratorio son opcionales porque una
    # consulta puede no tener prescripcion ni ordenes de lab).
    bloques_requeridos = [
        "Identificacion",
        "Historial de atenciones (ultimos 6 meses)",
        "Nota clinica de Yadira",
        "Diagnosticos",
        "Actividades",
        "Profesionales",
    ]

    for bloque in bloques_requeridos:
        contenido_bloque = bloques.get(bloque, "")
        if not contenido_bloque:
            faltantes.append(bloque)

    return faltantes


def re_extraer_bloque(
    driver: WebDriver,
    logger: logging.Logger,
    bloque: str,
    click_ok: bool,
    identificacion: dict[str, str] | None = None,
    historial: str | None = None,
    anamnesis: str | None = None,
    motivo_consulta: str | None = None,
    diagnosticos: list[str] | None = None,
    actividades: list[str] | None = None,
    profesionales: list[str] | None = None,
    recetas: list[str] | None = None,
    laboratorio: list[str] | None = None,
) -> str | list[str] | dict[str, str] | None:
    """Re-extrae especificamente el bloque faltante desde Rayen.

    Sesion 2026-09-16 14:14 (regla Yadira): si validar_nota_clinica
    detecta un bloque vacio, el pipeline llama a esta funcion con el
    `driver` que sigue en la ficha del paciente (estamos dentro del
    mismo loop, no hemos navegado a otra ficha).

    NOTA: el `driver` aqui deberia estar todavia en la ficha del
    paciente, pero NO se asume. Si `click_ok` fue False originalmente,
    no se puede extraer el bloque (no hay panel cargado). En ese caso
    retorna None.

    Returns:
        Contenido del bloque re-extraido, o None si no se pudo.
    """
    if not click_ok:
        # Sin click en "Atencion actual", no se puede extraer nada del panel.
        logger.warning(
            f"[crear_notas] re-extraer {bloque}: click_ok=False, no se "
            f"puede re-extraer (panel no cargo)."
        )
        return None

    if bloque == "Identificacion":
        return extraer_identificacion(driver, logger)
    if bloque == "Historial de atenciones (ultimos 6 meses)":
        return extraer_historial(driver, logger)
    if bloque == "Nota clinica de Yadira":
        # Anamnesis: si tenemos la original, intentar re-fetch.
        return extraer_anamnesis(driver, logger)
    if bloque == "Diagnosticos":
        return extraer_diagnosticos(driver, logger)
    if bloque == "Actividades":
        return extraer_actividades(driver, logger)
    if bloque == "Profesionales":
        return extraer_profesionales(driver, logger)
    if bloque == "Plan - Recetas":
        return extraer_recetas(driver, logger)
    if bloque == "Plan - Laboratorio":
        return extraer_laboratorio(driver, logger)

    logger.warning(f"[crear_notas] re-extraer: bloque desconocido '{bloque}'")
    return None


def paso_4_1_abrir_ficha(
    driver: WebDriver,
    logger: logging.Logger,
    paciente: PacienteObjetivo,
) -> bool:
    """Paso 4.1: filtra por fecha, busca al paciente por nombre, doble click.

    Devuelve True si abrio la ficha, False si no encontro al paciente.
    """
    logger.info(
        f"[crear_notas] 4.1 Paciente: {paciente.nombre} "
        f"| fecha={paciente.fecha} | tipo={paciente.tipo_atencion}"
    )

    # 4.1.a: filtrar por fecha
    select_date(driver, logger, fecha_str=paciente.fecha)
    sort_by_estado(driver, logger)

    # 4.1.b: buscar al paciente por nombre completo
    resultado_busqueda = _buscar_paciente_en_tabla(driver, logger, paciente.nombre)
    if resultado_busqueda is None:
        logger.warning(
            f"[crear_notas] No se encontro a '{paciente.nombre}' "
            f"en la tabla del {paciente.fecha}"
        )
        return False
    row, nombre_rayen = resultado_busqueda
    # Si hubo match parcial, guardar el nombre real de Rayen como
    # metadato para que Mortadelo pueda matchear despues.
    if nombre_rayen is not None:
        paciente.nombre_rayen = nombre_rayen

    # 4.1.c: doble click en la fila para abrir la ficha
    _doble_click_en_paciente(driver, logger, row, nombre_objetivo=paciente.nombre)

    # Esperar a que el panel del paciente se cargue. Senal inequivoca:
    # la tabla de identificacion del paciente tiene <th> en <tbody>
    # (par label:valor). La tabla de Pacientes citados tiene <th> solo
    # en <thead>, asi que el xpath con [.//tbody/th] filtra
    # especificamente la del paciente.
    #
    # Sesion 2026-09-09: timeout subido de 15s a 30s. Caso Ana Patricia
    # Vivanco Munoz: el panel tarda >15s en cargar y el script
    # seguia con extraccion sobre un panel vacio, generando una nota
    # con placeholders "(no se pudo extraer...)". Con 30s cubrimos el
    # percentil alto de paginas lentas de Rayen sin penalizar el caso
    # normal (las paginas rapidas cargan en <5s).
    panel_xpath = (
        "//table[.//tbody/th] | "
        "//li[@id='anamnesis'] | "
        "//div[contains(@class,'side-card')]//*[contains(@class,'rct-tree')] | "
        # ECICEP-g3 a veces no tiene tabla de identificacion visible
        # (la estratificacion carga primero). Esperar el card tambien.
        "//*[contains(@class, 'stratification-card')]"
    )
    # Sesion 2026-09-16: 30s -> 60s para ECICEP-g3.
    # IMPORTANTE: NO hacer retry del doble-click aqui. El primer click
    # ya nos llevo a la ficha del paciente. Si el panel no cargo,
    # un segundo click no ayuda (la fila ya esta stale y ademas
    # get_pacientes_del_dia espera 15s por div.rt-tr-group que ya
    # no existe -> TimeoutException). Mejor: 1 sola espera de 60s,
    # si falla -> placeholder, navegar manualmente al siguiente.
    panel_timeout = 60
    panel = _wait_visible(driver, panel_xpath, timeout=panel_timeout)

    if panel is None:
        # Panel no cargo en 60s. NO re-clickamos. Marcamos el flag y
        # dejamos que la extraccion proceda (devuelve vacios). La nota
        # se guarda con placeholders + flag REVISION.
        logger.warning(
            f"[crear_notas] Panel no aparecio en {panel_timeout}s. "
            f"Extraccion procedera sobre lo que haya; "
            f"guardar_nota_clinica() escribira placeholder con flag REVISION."
        )
        paciente.panel_cargo = False
    else:
        logger.info(
            f"[crear_notas] Panel del paciente cargado ({panel.tag_name})"
        )

    logger.info(
        f"[crear_notas] Ficha abierta para {paciente.nombre} "
        f"(URL actual: {driver.current_url})"
    )
    return True


# ---- Iterador principal (paso 4.6: sigue con el siguiente) ----

def iterar_pacientes(
    driver: WebDriver,
    logger: logging.Logger,
    pacientes: list[PacienteObjetivo],
) -> dict[str, int]:
    """Por cada paciente: ejecutar paso 4.1. Si falla, sigue con el siguiente."""
    stats = {"procesados": 0, "abiertos": 0, "no_encontrados": 0, "errores": 0}
    for i, p in enumerate(pacientes, 1):
        logger.info(
            f"[crear_notas] ({i}/{len(pacientes)}) "
            f"Procesando: {p.nombre} ({p.fecha})"
        )
        try:
            stats["procesados"] += 1
            ok = paso_4_1_abrir_ficha(driver, logger, p)
            if ok:
                stats["abiertos"] += 1
            else:
                stats["no_encontrados"] += 1
        except Exception as e:  # noqa: BLE001
            stats["errores"] += 1
            logger.error(
                f"[crear_notas] Error con {p.nombre}: {e}. "
                f"Sigue con el siguiente."
            )
            continue
    return stats


# ---- Main ----

def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Crear notas clinicas desde Rayen. "
            "Por defecto procesa UN paciente (--paciente + --fecha). "
            "Con --todos procesa los pacientes del informe del mes en curso."
        )
    )
    parser.add_argument(
        "--paciente",
        type=str,
        default=None,
        help="Nombre completo del paciente a procesar (modo 1 paciente).",
    )
    parser.add_argument(
        "--fecha",
        type=str,
        default=None,
        help="Fecha del paciente en formato dd-mm-yyyy (modo 1 paciente).",
    )
    parser.add_argument(
        "--todos",
        action="store_true",
        help="Procesa los pacientes del informe del mes en curso (modo batch).",
    )
    parser.add_argument(
        "--informe",
        type=Path,
        default=None,
        help=(
            "Path al informe MENSUAL de fichas abiertas "
            f"(default: {_informe_mes_actual_path().name}). "
            "NO usar el informe anual (_completo.txt) — esta prohibido."
        ),
    )
    parser.add_argument(
        "--user",
        type=str,
        default="yadira",
        help="Usuario de config/users.json (default: yadira)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    # Default de --informe: el informe del mes en curso.
    if args.informe is None:
        args.informe = _informe_mes_actual_path()

    # Guard: el informe anual (_completo) NO se puede usar con --todos.
    # Es una operacion distinta, para otros propositos, y no debe
    # mezclarse con el batch mensual. Si llega por error, abortar claro.
    if args.todos and "_completo" in args.informe.name:
        parser.error(
            f"REFUSADO: {args.informe.name} es el informe ANUAL, "
            f"no se puede usar con --todos. "
            f"Usa el informe del mes en curso ({_informe_mes_actual_path().name}) "
            f"o pasa --informe con un path mensual explicito."
        )

    # Validar modo
    if not args.todos and (not args.paciente or not args.fecha):
        parser.error("Modo 1 paciente requiere --paciente y --fecha. O usa --todos.")

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logger = logging.getLogger("crear_notas_clinicas")

    # 1. Cargar credenciales
    try:
        credentials = load_credentials(args.user)
    except (FileNotFoundError, ValueError) as e:
        logger.error(f"Error cargando credenciales: {e}")
        return 2
    logger.info(f"[crear_notas] Credenciales cargadas para usuario: {args.user}")

    # 2. Construir la lista de pacientes
    if args.todos:
        pacientes = parsear_informe(args.informe)
        logger.info(
            f"[crear_notas] Modo --todos: {len(pacientes)} pacientes del informe {args.informe.name}"
        )
    else:
        pacientes = [
            PacienteObjetivo(
                fecha=args.fecha,
                nombre=args.paciente,
                tipo_atencion="(no se valida contra informe)",
                razon="",
            )
        ]
        logger.info(
            f"[crear_notas] Modo 1 paciente: {pacientes[0].nombre} | {pacientes[0].fecha}"
        )

    # 3. Pasos 1-3: login + box + Pacientes citados (via run_login)
    driver: Optional[WebDriver] = None
    stats = {"procesados": 0, "abiertos": 0, "guardados": 0, "saltados": 0, "errores": 0}
    fichas_en_sesion = 0
    # Carpeta donde Chrome dejara los adjuntos descargados. Se crea
    # aca para que exista cuando _build_chrome_options la reciba.
    ADJUNTOS_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    # Capturador de warnings para el informe tecnico (separado de la ficha).
    warnings_collector = WarningsCollector()
    warnings_collector.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    )
    logging.getLogger("crear_notas").addHandler(warnings_collector)
    # Lista de informes por paciente.
    pacientes_informe: list[PacienteInforme] = []
    import time as _time
    logger.info(
        f"[crear_notas] Download dir Chrome: {ADJUNTOS_DOWNLOAD_DIR.resolve()}"
    )
    try:
        driver = run_login(
            credentials,
            logger,
            download_dir=str(ADJUNTOS_DOWNLOAD_DIR.resolve()),
        )
        if not ensure_session_alive(driver, logger):
            logger.error("Sesion invalida tras login.")
            return 1
        logger.info("[crear_notas] Login + navegacion OK.")

        # 4. Por cada paciente: 4.1 (abrir ficha) + 4.2 (extraer) + 4.3 (guardar)
        notas_dir = ROOT / "notas_clinicas"
        for i, paciente in enumerate(pacientes, 1):
            t_inicio = _time.time()
            warnings_collector.reset()  # snapshot limpio por paciente
            logger.info(
                f"[crear_notas] ({i}/{len(pacientes)}) "
                f"Procesando: {paciente.nombre} ({paciente.fecha})"
            )
            stats["procesados"] += 1
            ficha_ok = False
            pinfo = PacienteInforme(
                nombre=paciente.nombre,
                fecha=paciente.fecha,
            )
            try:
                # Paso 4.1
                ok = paso_4_1_abrir_ficha(driver, logger, paciente)
                if not ok:
                    logger.warning(
                        f"[crear_notas] No se encontro a {paciente.nombre} en la tabla. Saltando."
                    )
                    stats["saltados"] += 1
                    pinfo.estado = "skipped"
                    pinfo.match_tipo = "ninguno"
                    pinfo.warnings = warnings_collector.snapshot()
                    pacientes_informe.append(pinfo)
                    continue
                stats["abiertos"] += 1
                ficha_ok = True
                # Si hubo match parcial, paso_4_1 setea paciente.nombre_rayen.
                if paciente.nombre_rayen:
                    pinfo.match_tipo = "parcial"
                    pinfo.match_nombre_rayen = paciente.nombre_rayen
                else:
                    pinfo.match_tipo = "exacto"

                # Paso 4.2
                # ORDEN 2026-08-26 (Miguel): estratificacion ECICEP PRIMERO.
                # Razon: la estratificacion abre un modal; hay que cerrarlo
                # con el boton "Salir" antes de cualquier otra extraccion, para
                # que el overlay/modal no intercepte clicks posteriores.
                # 1) Estratificacion (incluye apertura popover+modal, parseo
                #    y cierre via boton "Salir" + cierre de popover).
                # 2) Identificacion, 3) Historial.
                # 4) Click en Atencion actual.
                # 5) Motivo, 6) Anamnesis, 7) Diagnostico, 8) Actividad,
                #    9) Profesionales, 10) Plan -> Recetas, 11) Plan -> Laboratorio.
                # Fuera de scope: examenes adjuntos, pautas, otros items,
                # plan -> imagenologia, plan -> interconsulta.
                estratificacion = extraer_estratificacion_ecicep(driver, logger)
                identificacion = extraer_identificacion(driver, logger)
                # Historial ANTES del click en "Atencion actual" porque ese
                # click puede colapsar el panel del historial.
                historial = extraer_historial(driver, logger)
                # Secciones fuera de scope (no se extraen, se pasan vacias):
                examenes = ""
                # Ahora si hacemos click en Atencion actual
                click_ok = click_atencion_actual(driver, logger)
                motivo_consulta = (
                    extraer_motivo_consulta(driver, logger) if click_ok else ""
                )
                anamnesis = extraer_anamnesis(driver, logger) if click_ok else ""
                diagnosticos = (
                    extraer_diagnosticos(driver, logger) if click_ok else []
                )
                actividades = (
                    extraer_actividades(driver, logger) if click_ok else []
                )
                profesionales = (
                    extraer_profesionales(driver, logger) if click_ok else []
                )
                # Plan (panel derecho). Recetas y Laboratorio se extraen
                # del mismo panel #right-side-attention que ya esta visible
                # tras click_atencion_actual. Si click_ok fallo, no se
                # intenta (no hay panel que leer).
                recetas = (
                    extraer_recetas(driver, logger) if click_ok else []
                )
                # Regla Yadira 2026-08-26: si el tipo de atencion es
                # "Recetas", dejamos SOLO la prescripcion con la Vigencia
                # mas reciente en el bloque PLAN RECETAS del .txt. Para
                # cualquier otro tipo, se conservan todas las recetas.
                if _tipo_atencion_es_recetas(paciente.tipo_atencion) and len(
                    recetas
                ) > 1:
                    recetas_filtradas = _filtrar_receta_mas_reciente(recetas)
                    logger.info(
                        f"[crear_notas] tipo=Recetas: filtradas "
                        f"{len(recetas)} -> {len(recetas_filtradas)} "
                        f"prescripcion(es) (mas reciente)"
                    )
                    recetas = recetas_filtradas
                laboratorio = (
                    extraer_laboratorio(driver, logger) if click_ok else []
                )
                # Fuera de scope:
                pautas = []
                otros_items = {}

                pinfo.extraccion = {
                    "identificacion_campos": len(identificacion),
                    "historial_caracteres": len(historial or ""),
                    "anamnesis_caracteres": len(anamnesis or ""),
                    "motivo_consulta_caracteres": len(motivo_consulta or ""),
                    "diagnosticos": len(diagnosticos or []),
                    "actividades": len(actividades or []),
                    "profesionales": len(profesionales or []),
                    "pautas": len(pautas or []),
                    "examenes_adjuntos_chars": len(examenes or ""),
                    "recetas_prescripciones": len(recetas or []),
                    "laboratorio_ordenes": len(laboratorio or []),
                    "estratificacion_grupo": (
                        (estratificacion or {}).get("grupo")
                    ),
                    "estratificacion_cronicos": len(
                        (estratificacion or {}).get("cronicos") or []
                    ),
                    "estratificacion_agudos": len(
                        (estratificacion or {}).get("agudos") or []
                    ),
                }

                # Paso 4.3
                try:
                    out_path = guardar_nota_clinica(
                        paciente, identificacion, historial, anamnesis,
                        diagnosticos, actividades, profesionales, pautas,
                        examenes, otros_items, estratificacion,
                        motivo_consulta, recetas, laboratorio, notas_dir,
                        panel_cargo=paciente.panel_cargo,
                    )
                    # Paso 4.4: VALIDACION POST-WRITE + RE-FETCH DE HUECOS.
                    # Regla Yadira 2026-09-16 14:14: despues de escribir,
                    # el script verifica que todos los bloques tengan
                    # contenido. Si falta alguno, va a buscarlo a Rayen
                    # con el `driver` que sigue activo y sobrescribe el
                    # archivo.
                    faltantes = validar_nota_clinica(out_path)
                    if faltantes:
                        logger.warning(
                            f"[crear_notas] {paciente.nombre}: "
                            f"validacion post-write encontro {len(faltantes)} "
                            f"bloque(s) sin contenido: {faltantes}. "
                            f"Re-fetch + re-write."
                        )
                        bloques_reescritos: list[str] = []
                        bloques_aun_vacios: list[str] = []
                        for bloque in faltantes:
                            nuevo = re_extraer_bloque(
                                driver, logger, bloque, click_ok,
                                identificacion=identificacion,
                                historial=historial,
                                anamnesis=anamnesis,
                                motivo_consulta=motivo_consulta,
                                diagnosticos=diagnosticos,
                                actividades=actividades,
                                profesionales=profesionales,
                                recetas=recetas,
                                laboratorio=laboratorio,
                            )
                            if nuevo:
                                _rellenar_bloque_en_nota(
                                    out_path, bloque, nuevo
                                )
                                bloques_reescritos.append(bloque)
                            else:
                                bloques_aun_vacios.append(bloque)
                        if bloques_reescritos:
                            logger.info(
                                f"[crear_notas] {paciente.nombre}: "
                                f"re-fetch completo para {bloques_reescritos}."
                            )
                        if bloques_aun_vacios:
                            logger.warning(
                                f"[crear_notas] {paciente.nombre}: "
                                f"no se pudo re-extraer: {bloques_aun_vacios}. "
                                f"Yadira debera revisar manualmente."
                            )

                    stats["guardados"] += 1
                    pinfo.estado = "ok"
                    logger.info(
                        f"[crear_notas] {paciente.nombre} OK -> "
                        f"{out_path.name}"
                    )
                except ValueError as ve:
                    # Regla Yadira 2026-09-16 14:50 (correccion): NO
                    # escribir markers. Si la extraccion fallo, el
                    # script debe REINTENTAR (re-click en 'Atencion
                    # actual' + re-extraer anamnesis) hasta N veces.
                    # Solo si agota todos los reintentos, skip
                    # silencioso (Yadira re-corre cuando Rayen este
                    # estable).
                    stats["errores_extraccion"] = (
                        stats.get("errores_extraccion", 0) + 1
                    )
                    pinfo.errores.append(f"ValueError: {ve!r}")
                    out_reintento = _reintentar_extraccion_anamnesis(
                        driver, logger, paciente, click_ok,
                        identificacion, historial, diagnosticos,
                        actividades, profesionales, recetas,
                        laboratorio, examenes, otros_items,
                        estratificacion, motivo_consulta, pautas,
                        notas_dir,
                    )
                    if out_reintento is not None:
                        stats["guardados"] += 1
                        pinfo.estado = "ok"
                        logger.info(
                            f"[crear_notas] {paciente.nombre} OK "
                            f"(tras reintento) -> {out_reintento.name}"
                        )
                    else:
                        pinfo.estado = "extraccion_fallida"
                        logger.error(
                            f"[crear_notas] {paciente.nombre}: "
                            f"extraccion fallo tras agotar reintentos. "
                            f"Yadira re-corre cuando Rayen este estable."
                        )

            except Exception as e:  # noqa: BLE001
                stats["errores"] += 1
                pinfo.estado = "error"
                # Guardar tipo de excepcion + mensaje. Mensajes vacios ("Message: \n")
                # son tipicos de WebDriverException con msg vacio; el TIPO es lo
                # unico que da pista del problema real.
                import traceback as _tb
                err_repr = f"{type(e).__name__}: {e!r}"
                pinfo.errores.append(err_repr)
                tb_short = _tb.format_exc().splitlines()[-3:]
                logger.error(
                    f"[crear_notas] Error con {paciente.nombre}: {err_repr}. "
                    f"Ultimas lineas del traceback: {tb_short}. "
                    f"Sigue con el siguiente."
                )

            pinfo.warnings = warnings_collector.snapshot()
            pinfo.tiempo_segundos = round(_time.time() - t_inicio, 2)
            pacientes_informe.append(pinfo)

            # Despues de CADA paciente (exitoso o no), volver a la lista
            # para el siguiente. Y si llegamos al limite, resetear sesion.
            if ficha_ok:
                fichas_en_sesion += 1
            quedan = len(pacientes) - i
            necesita_reset = (
                fichas_en_sesion >= MAX_FICHAS_POR_SESION and quedan > 0
            )
            if necesita_reset:
                logger.warning(
                    f"[crear_notas] Limite de {MAX_FICHAS_POR_SESION} fichas alcanzado. "
                    f"Reseteando sesion de Rayen..."
                )
                safe_quit(driver, logger)
                driver = None
                driver = run_login(
                    credentials,
                    logger,
                    download_dir=str(ADJUNTOS_DOWNLOAD_DIR.resolve()),
                )
                if not ensure_session_alive(driver, logger):
                    logger.error("Sesion invalida tras re-login.")
                    return 1
                fichas_en_sesion = 0
            elif quedan > 0:
                # Volver a la lista de Pacientes citados para el siguiente
                volver_a_pacientes_citados(driver, logger)

        logger.info(
            f"[crear_notas] === Resumen final === "
            f"procesados={stats['procesados']}, "
            f"abiertos={stats['abiertos']}, "
            f"guardados={stats['guardados']}, "
            f"saltados={stats['saltados']}, "
            f"errores={stats['errores']}"
        )

        # Verificacion de target: el informe dice N fichas abiertas, el
        # script tiene que procesar las N. Si falta alguna, alertar.
        if args.todos:
            total_objetivo = len(pacientes)
            total_ok = stats["abiertos"]
            faltantes = total_objetivo - total_ok
            if faltantes > 0:
                logger.warning(
                    f"[crear_notas] === TARGET NO CUMPLIDO === "
                    f"Objetivo informe: {total_objetivo} fichas, "
                    f"abiertas OK: {total_ok}, "
                    f"FALTAN: {faltantes}. "
                    f"Revisar logs de 'No se encontro a ...' arriba."
                )
            else:
                logger.info(
                    f"[crear_notas] === TARGET OK === "
                    f"Las {total_objetivo} fichas del informe "
                    f"fueron procesadas."
                )

            # 5. Generar informe tecnico (JSON para Miguel).
            # Contiene warnings, errores, tiempos, datos extraidos por
            # paciente. NO va a la ficha, va a un archivo separado.
            informe = generar_informe_tecnico(
                modo="todos",
                informe=str(args.informe.name),
                pacientes=pacientes_informe,
                stats=stats,
            )
            informes_dir = ROOT / "data" / "analysis"
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            informe_path = informes_dir / f"informe_tecnico_{ts}.json"
            informe.guardar(informe_path)
            logger.info(
                f"[crear_notas] Informe tecnico guardado en: {informe_path}"
            )

        # 6. Cerrar navegador automaticamente al terminar
        logger.info("[crear_notas] Cerrando navegador...")
        return 0
    except Exception as e:  # noqa: BLE001
        logger.error(f"[crear_notas] Error fatal: {e}")
        return 1
    finally:
        if driver is not None:
            safe_quit(driver, logger)


if __name__ == "__main__":
    sys.exit(main())
