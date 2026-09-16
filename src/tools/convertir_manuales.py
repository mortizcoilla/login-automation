"""Convierte todos los manuales MINSAL de manuales/*.pdf a markdown en manuales_md/.

Usa `src.tools.pdf_a_md.extract` para la conversion. Cada PDF se guarda en
manuales_md/<basename>/<basename>.md con:
- Frontmatter YAML (title, source, source_url, pages, year)
- Marcas <!-- p.N --> entre paginas (citables en el output del LLM)
- Texto limpio sin headers/footers repetidos

Configuracion "optima para este proceso":
- Output organizado por carpeta (un .md por manual, lugar para chuns hijos)
- Idempotente: si el .md ya existe, lo skipea
- Logging de progreso (paginas procesadas, tiempo, MB generados)
- Skip de archivos > --max-size MB (default 100 MB) — excluye CIE-10 y DSM-5
  por defecto ya que son enciclopedias mas que manuales. Se procesan con
  --max-size 200 si los querés.
- Index JSON con metadata de todos los manuales convertidos

Uso:
    python -m src.tools.convertir_manuales                   # convierte todos <100MB
    python -m src.tools.convertir_manuales --force           # re-convierte aunque exista
    python -m src.tools.convertir_manuales --max-size 200    # incluye CIE-10 + DSM-5
    python -m src.tools.convertir_manuales --only "ECICEP*" # solo manuales cuyo nombre matchea
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import sys
import time
from pathlib import Path

from src.tools.pdf_a_md import extract

ROOT = Path(__file__).resolve().parent.parent.parent
MANUALES_DIR = ROOT / "data" / "manuales"
OUTPUT_DIR = ROOT / "data" / "manuales_md"
INDEX_PATH = OUTPUT_DIR / "index.json"

# Por defecto CIE-10 y DSM-5 (enciclopedias) quedan fuera — son >30MB y
# consumen contexto del LLM sin aportar valor practico para una consulta
# clinica habitual. Si los necesitas, --max-size 200.
DEFAULT_MAX_SIZE_MB = 100
# Mapping de titulos semanticos para que el LLM pueda buscar por contenido.
# Sesion 2026-09-16: los titulos por defecto del PDF (primera linea del
# frontmatter) son genericos ("Capitulo1", "3", "Investigacion original ...")
# y no le sirven al LLM para retrieval. Este dict los reemplaza con titulos
# descriptivos que incluyen la patologia / tema / ano / organismo.
# Patrones no listados usan el titulo detectado (fallback).
MANUAL_TITLES: dict[str, str] = {
    # GPC MINSAL (Guias de Practica Clinica)
    "08_RE_GPC-EPOC-2019_v3":
        "Reporte de Evaluacion - GPC EPOC (Enfermedad Pulmonar Obstructiva Cronica) MINSAL 2019 v3",
    "2024.04.18_HIPERTENSION-ARTERIAL-EN-INFANCIA-Y-ADOLESCENCIA_v3":
        "Hipertension Arterial en Infancia y Adolescencia - Guia MINSAL 2024 v3",
    "GPC_alcohol_drogas_menores20_2013":
        "GPC Alcohol y Drogas en Menores de 20 Anos - MINSAL 2013",
    "GPC_depresion_2013":
        "GPC Depresion en Personas de 15 Anos y Mas - MINSAL 2013",
    "GPC_trastorno_ansioso_2018":
        "GPC Trastorno de Ansiedad - MINSAL 2018",
    "GUIA-CLINICA-DEPRESION-15-Y-MAS":
        "Guia Clinica Depresion en Personas de 15 Anos y Mas - MINSAL",
    "GuiaHTA":
        "Guia Clinica Hipertension Arterial - MINSAL",
    "Gu\u00eda de Pr\u00e1ctica Cl\u00ednica \u2014 Hipertensi\u00f3n Arterial Primaria o Esencial en personas de 15 a\u00f1os y m\u00e1s":
        "Guia de Practica Clinica - Hipertension Arterial Primaria o Esencial en personas de 15 anos y m\u00e1s - MINSAL",
    "clinica-diabetes-mellitus-tipo-2-chile":
        "Guia Clinica Diabetes Mellitus Tipo 2 - Chile (MINSAL)",
    "epoc-gold-2026":
        "Estrategia GOLD 2026 - EPOC (Global Initiative for Chronic Obstructive Lung Disease)",
    "OT-PLANIFIC-Y-PROGRAMAC-2025-en-web":
        "Orientaciones Tecnicas Planificacion y Programacion en Red 2025 - MINSAL",
    "OT_ Instrumento de Evaluaci\u00f3n y certificaci\u00f3n del Modelo 2024_ v22012024":
        "Instrumento de Evaluacion y Certificacion del Modelo de Atencion 2024 v2 - MINSAL",

    # ECICEP (Estrategia de Cuidado Integral Centrado en las Personas)
    "DOC-ECICEP":
        "Documento ECICEP - Estrategia de Cuidado Integral Centrado en las Personas - MINSAL",
    "Lectura - Material Marco Referencial ECICEP 1":
        "Material Marco Referencial ECICEP - Lectura 1 - MINSAL",

    # Norma Tecnica Supervision Nino 0-9 anos (los 4 capitulos)
    "Capitulo-1-Web":
        "Capitulo 1 - Antecedentes Sociales y de Salud - Norma Tecnica Supervision Salud Integral Ninos 0-9 Anos - MINSAL 2021",
    "Capitulo-2-Web":
        "Capitulo 2 - Componentes Transversales y Especificos - Norma Tecnica Supervision Salud Integral Ninos 0-9 Anos - MINSAL 2021",
    "Capitulo-3-Web":
        "Capitulo 3 - Supervision de Salud Integral Infantil - Norma Tecnica Supervision Salud Integral Ninos 0-9 Anos - MINSAL 2021",
    "Capitulo-4-Web":
        "Capitulo 4 - Instrumentos para la Supervision - Norma Tecnica Supervision Salud Integral Ninos 0-9 Anos - MINSAL 2021",

    # Calendario / Inmunizaciones
    "CALENDARIO-INMUNIZACIONES-2026":
        "Calendario Nacional de Inmunizaciones 2026 - MINSAL (Programa Nacional de Inmunizaciones - PNI)",

    # Salud mental
    "construyendo_salud_mental_2024":
        "Construyendo Salud Mental 2024 - Documento MINSAL",
    "plan_nacional_sm_2017_2025":
        "Plan Nacional de Salud Mental 2017-2025 - MINSAL Chile",
    "programa_nacional_prevencion_suicidio_2013":
        "Programa Nacional de Prevencion del Suicidio 2013 - MINSAL",
    "rpe11_programacion_sm_aps_2021":
        "Orientaciones Tecnicas Programacion Salud Mental APS 2021 - MINSAL (RPE 11)",

    # Operativos / Estrategias
    "Manual-Operativo-IHAN_2025.2":
        "Manual Operativo IHAN (Iniciativa Hospital Amigo del Nino y de la Nina) 2025 v2 - MINSAL",
    "Marco-operativo_-Estrategia-de-cuidado-integral-centrado-en-las-personas":
        "Marco Operativo - Estrategia de Cuidado Integral Centrado en las Personas - MINSAL",
    "ley_21331_guia_diprece_2022":
        "Guia Ley 21.331 (Ley de Buen Trato y Cuidado Digno) - DIPRECE 2022 - MINSAL",
    "Orientaciones-2019-":
        "Orientaciones Tecnicas 2019 - MINSAL",

    # Codigos / clasificaciones
    "CIE-10_2018_VOL1":
        "CIE-10 (Clasificacion Internacional de Enfermedades, 10a ed.) Volumen 1 - MINSAL/OMS 2018",
    "CIE-10_2018_VOL2":
        "CIE-10 (Clasificacion Internacional de Enfermedades, 10a ed.) Volumen 2 - MINSAL/OMS 2018",
    "CIE-10_2018_VOL3":
        "CIE-10 (Clasificacion Internacional de Enfermedades, 10a ed.) Volumen 3 - MINSAL/OMS 2018",
    "dsm5":
        "DSM-5 (Manual Diagnostico y Estadistico de los Trastornos Mentales, 5a ed.) - APA",

    # Articulos / papers
    "articles-655_recurso_1":
        "Articulo Cientifico - Recurso Academico 1",
    "articulo-de-revision-1":
        "Articulo de Revision 1",
    "e160":
        "Investigacion Original Pan American Journal - e160",
    "es":
        "Investigacion Original Pan American Journal - es",
    "RSC-Vol2-Cap3":
        "Revista Salud Comunitaria UANDES Vol. 2 - Capitulo 3 - 2024",
    "S0300893218306791":
        "Articulo Cientifico (Elsevier identifier S0300893218306791)",

    # Informes tecnicos
    "Sg-10_Informe-de-B\u00fasqueda-y-sintesis-de-efectividad_GPC-EPOC-2019":
        "Informe de Busqueda y Sintesis de Efectividad - GPC EPOC 2019 (Sg-10) - MINSAL",
    "T1_informe-busqueda-sintesis-efectividad-GPC-HTA-2018":
        "Informe T1 - Busqueda y Sintesis de Efectividad - GPC HTA 2018 - MINSAL",
    "T4_Informe-de-B\u00fasqueda-y-s\u00edntesis-de-VyP-de-los-pacientes_GPC-HTA-2018":
        "Informe T4 - Busqueda y Sintesis de Valores y Preferencias de Pacientes - GPC HTA 2018 - MINSAL",
}

def convertir_uno(
    pdf_path: Path,
    out_root: Path,
    source_url: str = "",
    year: str | None = None,
    force: bool = False,
    title_override: str | None = None,
) -> Path | None:
    """Convierte un PDF a markdown. Devuelve el path del .md o None si se skipeo.

    - Si out_root/<basename>.md existe y no --force, devuelve None.
    - Crea out_root/<basename>/ y guarda out_root/<basename>/<basename>.md.
      Asi queda lugar para chunks hijos o assets si en el futuro se divide.
    """
    basename = pdf_path.stem
    target_dir = out_root / basename
    target_md = target_dir / f"{basename}.md"
    if target_md.exists() and not force:
        logging.info(f"  SKIP {pdf_path.name} (ya existe)")
        return None
    target_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        extract(
            pdf_path,
            target_md,
            source_url=source_url,
            year=year,
            title_override=title_override,
        )
    except Exception as e:
        logging.error(f"  ERROR {pdf_path.name}: {e}")
        return None
    elapsed = time.time() - t0
    size_mb = target_md.stat().st_size / (1024 * 1024)
    logging.info(
        f"  OK {pdf_path.name} -> {target_md.relative_to(ROOT)} "
        f"({size_mb:.2f} MB, {elapsed:.1f}s)"
    )
    return target_md


def iterar_manuales(
    manuales_dir: Path,
    max_size_mb: int,
    only: str | None = None,
) -> list[Path]:
    """Lista PDFs en manuales_dir. Filtra por tamano y patron."""
    if not manuales_dir.exists():
        return []
    pdfs = sorted(manuales_dir.glob("*.pdf"))
    if only:
        pdfs = [p for p in pdfs if fnmatch.fnmatch(p.name, only)]
    return [p for p in pdfs if p.stat().st_size <= max_size_mb * 1024 * 1024]


def escribir_index(out_root: Path, manuales_dir: Path) -> None:
    """Genera manuales_md/index.json con metadata de todos los .md generados."""
    if not out_root.exists():
        return
    entradas: list[dict] = []
    for d in sorted(out_root.iterdir()):
        if not d.is_dir():
            continue
        for md in d.glob("*.md"):
            stat = md.stat()
            entradas.append({
                "id": d.name,
                "path": str(md.relative_to(ROOT)),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "mtime": time.strftime(
                    "%Y-%m-%dT%H:%M:%S", time.localtime(stat.st_mtime)
                ),
            })
    out_root.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(
            {
                "total": len(entradas),
                "size_mb_total": round(
                    sum(e["size_mb"] for e in entradas), 2
                ),
                "manuales": entradas,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    logging.info(
        f"Index escrito en {INDEX_PATH.relative_to(ROOT)} "
        f"({len(entradas)} manuales)"
    )


def main() -> int:
    p = argparse.ArgumentParser(
        description="Convierte manuales/*.pdf a markdown en manuales_md/."
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Re-convierte aunque el .md destino ya exista.",
    )
    p.add_argument(
        "--max-size",
        type=int,
        default=DEFAULT_MAX_SIZE_MB,
        help=f"Tamano maximo en MB. Default: {DEFAULT_MAX_SIZE_MB} (excluye CIE-10 y DSM-5).",
    )
    p.add_argument(
        "--only",
        type=str,
        default=None,
        help='Patron glob para filtrar manuales por nombre (ej. "ECICEP*", "*HTA*").',
    )
    p.add_argument(
        "--source-url",
        type=str,
        default="https://minsal.cl/",
        help="URL base para el frontmatter source_url. Default: minsal.cl",
    )
    args = p.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    pdfs = iterar_manuales(
        MANUALES_DIR, max_size_mb=args.max_size, only=args.only
    )
    if not pdfs:
        logging.warning(
            f"Ningun PDF encontrado en {MANUALES_DIR} "
            f"(max_size={args.max_size}MB, only={args.only})"
        )
        return 1

    logging.info(
        f"Convirtiendo {len(pdfs)} manuales de {MANUALES_DIR} "
        f"a {OUTPUT_DIR}..."
    )
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    convertidos = 0
    for pdf in pdfs:
        # year: tomar del nombre o dejar None.
        year = None
        for y in range(2015, 2030):
            if str(y) in pdf.name:
                year = str(y)
                break
        # Titulo del mapping si esta disponible, sino None (usa el detectado).
        titulo_override = MANUAL_TITLES.get(pdf.stem)
        result = convertir_uno(
            pdf,
            OUTPUT_DIR,
            source_url=args.source_url,
            year=year,
            force=args.force,
            title_override=titulo_override,
        )
        if result is not None:
            convertidos += 1

    escribir_index(OUTPUT_DIR, MANUALES_DIR)
    logging.info(
        f"Listo: {convertidos}/{len(pdfs)} convertidos. "
        f"Index en {INDEX_PATH.relative_to(ROOT)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())