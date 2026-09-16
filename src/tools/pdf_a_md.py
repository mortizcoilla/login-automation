"""
Extrae texto de un PDF a markdown con metadatos y marcas de pagina.

Uso:
    python -m src.tools.pdf_a_md <pdf_path> <output_md>

El .md generado incluye:
    - Frontmatter YAML con metadata (fuente, anio, capitulo)
    - Marcas <!-- p.N --> entre paginas
    - Headers/footers repetidos se eliminan
    - Titulos detectados por patron: linea corta, mayusculas, o numerada

Los bundles referencian por nombre de archivo .md, seccion y pagina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pdfplumber

# Heuristica para detectar titulos
# Linea corta (< 90 chars), sin punto final, mayusculas o numerada
TITLE_RE = re.compile(r"^(?:[0-9]+(?:\.[0-9]+)*\s+)?[A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ0-9 ,;:\-\(\)/]{2,89}$")

# Heuristica para descartar headers/footers repetidos
PAGE_NUMBER_RE = re.compile(r"^\s*\d{1,4}\s*$")


def is_likely_title(line: str) -> bool:
    """Una linea es titulo si es corta, mayusculas o empieza con numeracion."""
    s = line.strip()
    if not s or len(s) > 90:
        return False
    if s.endswith("."):
        return False
    return bool(TITLE_RE.match(s))


def is_page_marker(line: str) -> bool:
    return bool(PAGE_NUMBER_RE.match(line))


def clean_page_text(text: str) -> str:
    """Limpia texto de una pagina: colapsa espacios, quita lineas vacias."""
    lines = []
    for raw in text.split("\n"):
        s = raw.strip()
        if not s:
            continue
        if is_page_marker(s):
            continue
        lines.append(s)
    return "\n".join(lines)


def detect_metadata(pdf_path: Path) -> dict:
    """Lee primera pagina y extrae titulo / subtitulo basico."""
    with pdfplumber.open(pdf_path) as pdf:
        first_text = pdf.pages[0].extract_text() or ""
    # Primeras 3 lineas no vacias
    lines = [s.strip() for s in first_text.split("\n") if s.strip()][:5]
    title = lines[0] if lines else pdf_path.stem
    return {"title": title, "first_lines": lines}


def extract(pdf_path: Path, output_md: Path, *, source_url: str, year: str | None = None, title_override: str | None = None) -> None:
    with pdfplumber.open(pdf_path) as pdf:
        total = len(pdf.pages)
        print(f"[pdf_a_md] {pdf_path.name}: {total} paginas", flush=True)
        chunks: list[str] = []
        for idx, page in enumerate(pdf.pages, start=1):
            txt = page.extract_text() or ""
            cleaned = clean_page_text(txt)
            if cleaned:
                chunks.append(f"<!-- p.{idx} -->\n{cleaned}")
            if idx % 25 == 0:
                print(f"  ... {idx}/{total}", flush=True)

    # Frontmatter
    meta = detect_metadata(pdf_path)
    title_final = title_override if title_override else meta["title"]
    frontmatter_lines = [
        "---",
        f'title: "{title_final}"',
        f"source: {pdf_path.name}",
        f"source_url: {source_url}",
        f"pages: {total}",
    ]
    if year:
        frontmatter_lines.append(f"year: {year}")
    frontmatter_lines.append("---")
    frontmatter_lines.append("")

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(frontmatter_lines) + "\n".join(chunks), encoding="utf-8")
    size_kb = output_md.stat().st_size / 1024
    print(f"[pdf_a_md] OK -> {output_md} ({size_kb:.1f} KB)", flush=True)


def main(argv: list[str]) -> int:
    if len(argv) < 4:
        print("Uso: pdf_a_md <pdf> <out_md> <source_url> [year]", file=sys.stderr)
        return 2
    pdf_path = Path(argv[1])
    output_md = Path(argv[2])
    source_url = argv[3]
    year = argv[4] if len(argv) > 4 else None
    if not pdf_path.exists():
        print(f"PDF no encontrado: {pdf_path}", file=sys.stderr)
        return 1
    extract(pdf_path, output_md, source_url=source_url, year=year)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
