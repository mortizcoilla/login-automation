"""REQ-104 fase 2: receta cronica vigente desde el arbol "Receta" del
historial (busca tambien en atenciones ANTERIORES a la de hoy).

Obligatoriedad de la busqueda en el pasado (diseno cerrado 11-10-2026,
escenario de Miguel): las prescripciones viven DENTRO de la atencion
donde fueron escritas — el panel Plan -> Recetas de la atencion actual
solo muestra lo recetado HOY. La cronica de una atencion pasada (el
losartan del hipertenso que viene por un resfrio) es INVISIBLE para el
plan actual: declararla inexistente por eso es el falso negativo
INACEPTABLE del diseño.

Superficie (definida por Miguel con HTML/capturas, vuelta 7-17):
 1. La apertura del paso 3 termina en "Historia clinica" (REQ-093);
    esta funcion corre ahi, SIN navegacion nueva.
 2. En el header del arbol "Historial de atenciones" hay un select de
    categoria #orderby-record. TRAMPA: el ID esta DUPLICADO en la
    pagina (el segundo, en el card de filtros oculto, tiene otras
    opciones). El VALIDO es el que contiene option[value="3"] con
    texto "Receta" — desambiguar por contenido, jamas por orden.
 3. Seleccionar "Receta" RE-RENDERIZA el arbol con el agregado de
    TODAS las recetas del paciente a traves de las atenciones, en
    ventana fija de 12 Meses (NO se toca #adverseReaction: las
    cronicas requieren renovacion en ciclos menores a 12 meses, asi
    que una cronica fuera de la ventana legitimamente no calza).
 4. Cada nodo toplevel: tree-mainText (fecha) + tree-secondaryText
    (lineas "Receta Nro. <num>, generada el <fecha hora>, tipo
    morbilidad|cronica|urgencia, estado ...[, fecha de despacho: ...]").
    VARIANTE urgencia: sin secondaryText, la linea va INLINE en
    mainText — por eso se parsea el TEXTO COMPLETO del li.
 5. Nodo ganador = el que contiene la linea cronica con "generada el"
    MAXIMA (se barren TODOS los nodos; no parar en el primero). El
    ESTADO (despachada/caducada/cerrada en farmacia) NO califica ni
    descarta: viaja dentro del texto verbatim.
 6. Expandir el ganador (click nativo en button.rct-collapse-btn) →
    hijo con titulo EXACTO "Receta(s)" (hay un hermano "Prescripcion(es)"
    que NO se toca; match por texto normalizado, jamas por contencion)
    → expandir SOLO los hijos cronica (match por Nro) → hojas
    li.rct-node-leaf con FARMACO + POSOLOGIA autovinculadas por la cola
    "de la Receta Nº <num>" (variantes Nº/Nro./Nro).

Salida tri-estado (anti-falso-negativo, vuelta 12):
  encontrada    → {fecha_nodo, bloque} verbatim (lineas cronica + su
                  farmaco debajo de cada una).
  no_existe     → SOLO con prueba positiva: categoria verificada en
                  "Receta" + arbol re-renderizado (lineas "Receta Nro"
                  presentes) + TODOS los nodos barridos + 0 cronicas.
  indeterminado → todo lo demas (select ausente, re-render timeout —
                  cubre el paciente sin NINGUNA receta, indistinguible
                  de un render fallido —, expansion fallida, excepcion).
                  Jamas se reporta como "no existe".
Evidencia __DEBUG__ en el log siempre (auditable post-hoc). Higiene:
restaurar "Diagnostico" (value 0) al terminar, colapsar best-effort.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

ESTADO_ENCONTRADA = "encontrada"
ESTADO_NO_EXISTE = "no_existe"
ESTADO_INDETERMINADO = "indeterminado"

_VALOR_RECETA = "3"
_VALOR_DIAGNOSTICO = "0"

# Una linea de receta del arbol (tolerante: prefijo "(1) ", "Nro." /
# "Nro" / "Nº", espacios antes de comas, tildes — el tipo se compara
# normalizado, no por posicion).
_RX_LINEA_RECETA = re.compile(
    r"Receta\s+Nro\.?\s*(?P<numero>\d+)\s*,\s*"
    r"generada el\s+(?P<generada>\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2})\s*,\s*"
    r"tipo\s+(?P<tipo>[a-zA-ZáéíóúÁÉÍÓÚ]+)\s*,\s*"
    r"estado\s+(?P<estado>[^,\n]+)\s*(?:,\s*fecha de despacho:\s*(?P<despacho>[\d\-]+))?",
    re.IGNORECASE,
)
# Cola de autovinculacion de las hojas de farmaco ("Nº"/"Nro."/"Nro").
_RX_FARMACO_RECETA = re.compile(r"de la Receta\s+N[ºo.]?\s*(\d+)", re.IGNORECASE)


def normalizar(texto: str) -> str:
    """Minusculas, sin tildes, espacios colapsados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sin_tildes).strip().lower()


def parsear_lineas_receta(texto_nodo: str) -> list[dict]:
    """Lineas de receta de un nodo (texto completo del li).

    Devuelve una entrada por linea que calce la regex, con el numero,
    la fecha "generada el" cruda, el tipo NORMALIZADO (cronica,
    morbilidad, urgencia), el estado y la linea VERBATIM.
    """
    out: list[dict] = []
    for linea in (texto_nodo or "").splitlines():
        m = _RX_LINEA_RECETA.search(linea)
        if not m:
            continue
        out.append(
            {
                "numero": m.group("numero"),
                "generada": m.group("generada"),
                "tipo": normalizar(m.group("tipo")),
                "estado": m.group("estado").strip(),
                "linea": linea.strip(),
            }
        )
    return out


def _parsear_generada(generada: str) -> datetime | None:
    try:
        return datetime.strptime(generada.strip(), "%d-%m-%Y %H:%M")
    except (ValueError, TypeError):
        return None


def seleccionar_ganador(nodos: list[dict]) -> dict | None:
    """Nodo que contiene la linea CRONICA con "generada el" maxima.

    Se barren TODOS los nodos (la cronica mas reciente puede convivir
    con recetas de morbilidad mas nuevas). Sin fechas parseables en una
    linea cronica, esa linea no participa (no se inventa recencia).
    None si ningun nodo trae cronicas.
    """
    mejor: tuple[datetime, dict] | None = None
    for nodo in nodos:
        for linea in nodo["lineas"]:
            if linea["tipo"] != "cronica":
                continue
            dt = _parsear_generada(linea["generada"])
            if dt is None:
                continue
            if mejor is None or dt > mejor[0]:
                mejor = (dt, nodo)
    return mejor[1] if mejor else None


def vincular_farmacos(lineas_cronicas: list[dict], hojas: list[str]) -> list[str]:
    """Lineas del bloque: cada cronica con SU farmaco/posologia DEBAJO.

    Las hojas se autovinculan por la cola "de la Receta Nº <num>".
    Hojas sin cola viable (variante no vista) van al final del bloque:
    no se pierden, no se inventa atribucion.
    """
    bloque: list[str] = []
    usadas: set[int] = set()
    for lc in lineas_cronicas:
        bloque.append(lc["linea"])
        for i, hoja in enumerate(hojas):
            if i in usadas:
                continue
            m = _RX_FARMACO_RECETA.search(hoja)
            if m and m.group(1) == lc["numero"]:
                bloque.append(hoja.strip())
                usadas.add(i)
    huerfanas = [
        h.strip() for i, h in enumerate(hojas) if i not in usadas and h.strip()
    ]
    return bloque + huerfanas


# ---------------------------------------------------------------------------
# Extractor Selenium (corre en "Historia clinica", REQ-093)
# ---------------------------------------------------------------------------

_TIMEOUT_EXPAND_SEG = 8


def _js_hay_select(valor: str, patron_texto: str) -> str:
    """JS: indice del orderby-record VALIDO para esa categoria, o '-1'.

    El ID esta duplicado en la pagina: el valido es el que contiene la
    option con ese value y el texto esperado ("Receta" / "Diagnóstico").
    """
    return (
        "const selects = Array.from(document.querySelectorAll('select#orderby-record'));"
        f"const rx = new RegExp('{patron_texto}', 'i');"
        "const valido = selects.find(s => Array.from(s.options).some("
        f"o => o.value === '{valor}' && rx.test((o.textContent || '').trim())));"
        "return valido ? String(selects.indexOf(valido)) : '-1';"
    )


_PATRON_TEXTO_CATEGORIA = {_VALOR_RECETA: "receta", _VALOR_DIAGNOSTICO: "diagn"}

_JS_ARBOL_TIENE_RECETA_NRO = (
    "const trees = Array.from(document.querySelectorAll('div.react-checkbox-tree'));"
    "for (const t of trees) {"
    "  if ((t.textContent || '').includes('Receta Nro')) return true;"
    "} return false;"
)

_JS_BARRER_NODOS = r"""
const trees = Array.from(document.querySelectorAll('div.react-checkbox-tree'));
const tree = trees.find(t => t.querySelector('.tree-mainText')) || null;
if (!tree) return JSON.stringify({debug: {arbol: false}, nodos: []});
const ol = tree.querySelector(':scope > ol') || tree.querySelector('ol');
const lis = ol
    ? Array.from(ol.children).filter(
          li => li.tagName === 'LI' && li.classList.contains('rct-node'))
    : [];
const nodos = lis.map((li, i) => ({
    indice: i,
    fecha: ((li.querySelector('.tree-mainText span') || {}).textContent || '').trim(),
    texto: (li.textContent || '').trim(),
}));
return JSON.stringify({debug: {arbol: true, toplevel: nodos.length}, nodos: nodos});
"""


def _seleccionar_categoria(driver: WebDriver, logger: logging.Logger, valor: str) -> bool:
    """Marca la categoria en el orderby-record VALIDO (click nativo).

    Devuelve False si el select valido no se encuentra.
    """
    try:
        idx = int(
            driver.execute_script(
                _js_hay_select(valor, _PATRON_TEXTO_CATEGORIA[valor])
            )
        )
    except Exception:
        idx = -1
    if idx < 0:
        logger.warning("[receta_cronica] orderby-record valido no encontrado")
        return False
    try:
        selects = driver.find_elements(By.CSS_SELECTOR, "select#orderby-record")
        select = selects[idx]
        opcion = select.find_element(By.CSS_SELECTOR, f'option[value="{valor}"]')
        opcion.click()  # click nativo; React re-renderiza el arbol
        return True
    except Exception as e:
        logger.warning(
            "[receta_cronica] no se pudo seleccionar categoria %s: %s", valor, e
        )
        return False


def _esperar_condicion(driver: WebDriver, js: str, timeout_seg: float) -> bool:
    fin = time.time() + timeout_seg
    while time.time() < fin:
        try:
            if driver.execute_script(js):
                return True
        except Exception:
            pass  # estado intermedio del render: reintentar
        time.sleep(0.4)
    return False


def _esperar_expandido(li, timeout_seg: float = _TIMEOUT_EXPAND_SEG) -> bool:
    fin = time.time() + timeout_seg
    while time.time() < fin:
        try:
            if "rct-node-expanded" in (li.get_attribute("class") or ""):
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _hijos_directos(li):
    try:
        return [
            h
            for h in li.find_elements(By.XPATH, "./ol/li[contains(@class, 'rct-node')]")
            or []
        ]
    except Exception:
        return []


def _higiene(driver: WebDriver, logger: logging.Logger) -> None:
    """Restaurar "Diagnostico" (best-effort; jamas bota el paso 3)."""
    try:
        _seleccionar_categoria(driver, logger, _VALOR_DIAGNOSTICO)
    except Exception:
        pass


def extraer_receta_cronica(
    driver: WebDriver, logger: logging.Logger, timeout_render_seg: float = 15.0
) -> dict:
    """Pipeline completo. NUNCA lanza: cualquier fallo = indeterminado.

    Retorna {estado, fecha_nodo, bloque, intentos, evidencia}.
    """
    evidencia: dict = {}
    resultado = {
        "estado": ESTADO_INDETERMINADO,
        "fecha_nodo": "",
        "bloque": "",
        "intentos": 0,
        "evidencia": "",
    }
    try:
        resultado = _pipeline(driver, logger, timeout_render_seg, evidencia)
    except Exception as e:
        evidencia["excepcion"] = f"{type(e).__name__}: {e}"
        logger.warning("[receta_cronica] fallo -> indeterminado: %s", evidencia["excepcion"])
        resultado = {
            "estado": ESTADO_INDETERMINADO,
            "fecha_nodo": "",
            "bloque": "",
            "intentos": resultado.get("intentos", 0),
            "evidencia": "",
        }
    resultado["evidencia"] = json.dumps(evidencia, ensure_ascii=False)[:2000]
    logger.info("__DEBUG__ receta_cronica %s __DEBUG__", resultado["evidencia"])
    _higiene(driver, logger)
    return resultado


def _pipeline(
    driver: WebDriver,
    logger: logging.Logger,
    timeout_render_seg: float,
    evidencia: dict,
) -> dict:
    # 1) Categoria "Receta" en el orderby-record correcto.
    if not _seleccionar_categoria(driver, logger, _VALOR_RECETA):
        evidencia["select"] = "no_encontrado"
        return _indeterminado(evidencia)

    # 2) Re-render: el arbol debe mostrar lineas "Receta Nro". Timeout
    #    = indeterminado (cubre render fallido Y paciente sin NINGUNA
    #    receta: indistinguibles — vuelta 12 del diseno).
    if not _esperar_condicion(driver, _JS_ARBOL_TIENE_RECETA_NRO, timeout_render_seg):
        evidencia["render"] = "timeout_sin_receta_nro"
        return _indeterminado(evidencia)
    evidencia["render"] = "ok"

    # 3) Barrer TODOS los nodos toplevel.
    crudo = driver.execute_script(_JS_BARRER_NODOS) or "{}"
    datos = json.loads(crudo)
    evidencia.update(datos.get("debug", {}))
    nodos_crudos = datos.get("nodos") or []
    if not nodos_crudos:
        evidencia["barrido"] = "sin_nodos"
        return _indeterminado(evidencia)

    nodos = [
        {"indice": n["indice"], "fecha": n["fecha"], "lineas": parsear_lineas_receta(n["texto"])}
        for n in nodos_crudos
    ]
    total_lineas = sum(len(n["lineas"]) for n in nodos)
    cronicas = [l for n in nodos for l in n["lineas"] if l["tipo"] == "cronica"]
    evidencia["lineas_receta"] = total_lineas
    evidencia["cronicas"] = len(cronicas)

    # 4) no_existe SOLO con prueba positiva: arbol renderizado con
    #    lineas de receta visibles y 0 cronicas entre TODOS los nodos.
    if total_lineas == 0:
        evidencia["nota"] = "arbol sin lineas parseables"
        return _indeterminado(evidencia)
    if not cronicas:
        return {
            "estado": ESTADO_NO_EXISTE,
            "fecha_nodo": "",
            "bloque": "",
            "intentos": 1,
            "evidencia": "",
        }

    # 5) Ganador + farmacos de sus cronicas.
    ganador = seleccionar_ganador(nodos)
    assert ganador is not None  # cronicas no vacio => hay ganador
    lineas_cronicas = [l for l in ganador["lineas"] if l["tipo"] == "cronica"]
    hojas = _extraer_farmacos_ganador(driver, logger, ganador, lineas_cronicas, evidencia)
    bloque = "\n".join(
        [ganador["fecha"], *vincular_farmacos(lineas_cronicas, hojas)]
    ).strip()
    return {
        "estado": ESTADO_ENCONTRADA,
        "fecha_nodo": ganador["fecha"],
        "bloque": bloque,
        "intentos": 1,
        "evidencia": "",
    }


def _indeterminado(evidencia: dict) -> dict:
    return {
        "estado": ESTADO_INDETERMINADO,
        "fecha_nodo": "",
        "bloque": "",
        "intentos": 1,
        "evidencia": "",
    }


def _extraer_farmacos_ganador(
    driver: WebDriver,
    logger: logging.Logger,
    ganador: dict,
    lineas_cronicas: list[dict],
    evidencia: dict,
) -> list[str]:
    """Expande ganador -> hijo "Receta(s)" -> solo hijos cronica -> hojas.

    Fallo de expansion NO degrada el estado: la cronica ya esta
    verificada (anti-falso-negativo); el bloque sale sin farmacos y la
    evidencia lo marca.
    """
    numeros = {lc["numero"] for lc in lineas_cronicas}
    try:
        lis = driver.find_elements(
            By.CSS_SELECTOR, "div.react-checkbox-tree > ol > li.rct-node"
        )
        li = lis[ganador["indice"]]
        li.find_element(By.CSS_SELECTOR, "button.rct-collapse-btn").click()
        if not _esperar_expandido(li):
            evidencia["expansion"] = "ganador_timeout"
            return []

        hijo_recetas = next(
            (
                h
                for h in _hijos_directos(li)
                if normalizar(_titulo(h)) == "receta(s)"
            ),
            None,
        )
        if hijo_recetas is None:
            evidencia["expansion"] = "hijo_recetas_no_encontrado"
            return []
        hijo_recetas.find_element(By.CSS_SELECTOR, "button.rct-collapse-btn").click()
        if not _esperar_expandido(hijo_recetas):
            evidencia["expansion"] = "recetas_timeout"
            return []

        hojas: list[str] = []
        for hijo in _hijos_directos(hijo_recetas):
            texto = hijo.text or ""
            m = re.search(r"Nro\.?\s*(\d+)", texto, re.IGNORECASE)
            if not m or m.group(1) not in numeros:
                continue  # solo las cronicas del ganador
            hijo.find_element(By.CSS_SELECTOR, "button.rct-collapse-btn").click()
            if not _esperar_expandido(hijo):
                evidencia.setdefault("hojas_timeout", []).append(m.group(1))
                continue
            for hoja in hijo.find_elements(
                By.CSS_SELECTOR, "li.rct-node-leaf .rct-node-clickable"
            ):
                t = (hoja.text or "").strip()
                if t:
                    hojas.append(t)
        evidencia["hojas"] = len(hojas)
        return hojas
    except Exception as e:
        evidencia["expansion_excepcion"] = f"{type(e).__name__}: {e}"
        return []


def _titulo(li) -> str:
    try:
        return (li.find_element(By.CSS_SELECTOR, ".rct-node-clickable").text or "").strip()
    except Exception:
        return ""
