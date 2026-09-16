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
MANUALES_DIR = ROOT / "manuales"
OUTPUT_DIR = ROOT / "manuales_md"
INDEX_PATH = OUTPUT_DIR / "index.json"

# Por defecto CIE-10 y DSM-5 (enciclopedias) quedan fuera — son >30MB y
# consumen contexto del LLM sin aportar valor practico para una consulta
# clinica habitual. Si los necesitas, --max-size 200.
DEFAULT_MAX_SIZE_MB = 100


def convertir_uno(
    pdf_path: Path,
    out_root: Path,
    source_url: str = "",
    year: str | None = None,
    force: bool = False,
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
        extract(pdf_path, target_md, source_url=source_url, year=year)
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
        result = convertir_uno(
            pdf,
            OUTPUT_DIR,
            source_url=args.source_url,
            year=year,
            force=args.force,
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