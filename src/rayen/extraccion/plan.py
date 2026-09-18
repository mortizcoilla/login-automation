"""Plan de la atencion: recetas y ordenes de laboratorio.

REQ-029: si el tipo de atencion es Recetas, solo la prescripcion con
Vigencia mas reciente. Split de crear_notas_clinicas (Fase 3c).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import date as _date

from selenium.webdriver.remote.webdriver import WebDriver


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
        logger.info(f"[crear_notas] Recetas extraidas: {len(recetas)} prescripcion(es)")
        return recetas
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo recetas: {e}")
        return []


def extraer_laboratorio(driver: WebDriver, logger: logging.Logger) -> list[str]:
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
        laboratorio = [item for item in (result or []) if item]
        logger.info(f"[crear_notas] Laboratorio extraido: {len(laboratorio)} orden(es)")
        return laboratorio
    except Exception as e:
        logger.warning(f"[crear_notas] Error extrayendo laboratorio: {e}")
        return []


# ---- REQ-029: tipo=Recetas -> solo la prescripcion con Vigencia mas reciente ----
# Cuando el tipo de atencion es "Recetas", la ficha rellenada por Mortadelo
# debe incluir UNICAMENTE la prescripcion con la Vigencia mas reciente.
# Esto evita que se acumulen en el bloque Doctora sugerencias sobre recetas
# que ya fueron reemplazadas por una nueva.

_MONTHS_ES: dict[str, int] = {
    "ene": 1,
    "feb": 2,
    "mar": 3,
    "abr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "ago": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dic": 12,
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
    mes_num = _MONTHS_ES.get(mes_s.lower()[:4]) or _MONTHS_ES.get(mes_s.lower()[:3])
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
    t = "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")
    return t == "recetas"
