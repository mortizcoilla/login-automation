"""Paso 10 (Nivel 1): 'tu mes en numeros' — temas que trata Yadira.

Lee las notas clinicas (paso 3), extrae los codigos CIE-10 de la
seccion Diagnosticos (dos formatos: 'Clasificación: X' de la atencion
del dia y 'CIE-10: X' de los cronicos), la edad del paciente, y
agrega:
  - atenciones por capitulo CIE-10 (F = salud mental, I = cardiovascular...)
  - codigos mas frecuentes
  - distribucion de edad (adulto mayor = 60+)

SOLO LECTURA de notas; el output es un resumen agregado (sin nombres
ni datos identificables — REQ-044). Base para el boletin de lectura.
"""

from __future__ import annotations

import contextlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.core.rutas import NOTAS_DIR

# Capitulos CIE-10 que interesan para APS (primera letra del codigo).
CAPITULOS = {
    "A": "Infecciosas y parasitarias",
    "B": "Infecciosas y parasitarias",
    "C": "Tumores malignos",
    "D": "Tumores / sangre",
    "E": "Endocrinas y metabolicas",
    "F": "Salud mental",
    "G": "Sistema nervioso",
    "H": "Ojo y oido",
    "I": "Circulatorias",
    "J": "Respiratorias",
    "K": "Digestivas",
    "L": "Piel",
    "M": "Musculoesqueleticas",
    "N": "Genitourinarias",
    "O": "Embarazo / parto",
    "Q": "Congenitas",
    "R": "Sintomas y signos",
    "S": "Traumatismos",
    "T": "Traumatismos / intoxicaciones",
    "Z": "Factores de contacto con salud",
}

# 'Clasificación: H52Descripcion' (atencion del dia) y 'CIE-10: H52.7'
# (cronicos del ECICEP).
_CLASIFICACION_RE = re.compile(r"Clasificaci[oó]n:\s*([A-Z]\d{2}(?:\.\d)?)")
_CRONICO_RE = re.compile(r"CIE-10:\s*([A-Z]\d{2}(?:\.\d)?)")
_EDAD_RE = re.compile(r"Paciente[^\n]{0,40}?(\d{1,3})\s+a[ñn]os")


@dataclass
class ResumenTemas:
    """Agregado de un lote de notas. Solo datos agregados."""

    notas_leidas: int = 0
    notas_sin_cie: int = 0
    capitulos: Counter = field(default_factory=Counter)
    codigos: Counter = field(default_factory=Counter)
    edades: list[int] = field(default_factory=list)
    detalles: list[str] = field(default_factory=list)  # para el markdown

    def adulto_mayor(self) -> int:
        return sum(1 for e in self.edades if e >= 60)

    def con_edad(self) -> int:
        return len(self.edades)


def _capitulo(codigo: str) -> str:
    return CAPITULOS.get(codigo[0].upper(), f"Otro ({codigo[0]})")


def extraer_de_nota(texto: str) -> tuple[list[str], int | None]:
    """Codigos CIE-10 (unicos, en orden) y edad de UNA nota."""
    codigos: list[str] = []
    for regex in (_CLASIFICACION_RE, _CRONICO_RE):
        for m in regex.finditer(texto):
            codigo = m.group(1)
            if codigo not in codigos:
                codigos.append(codigo)
    edad = None
    m_edad = _EDAD_RE.search(texto)
    if m_edad:
        with contextlib.suppress(ValueError):
            edad = int(m_edad.group(1))
    return codigos, edad


def analizar_notas(notas_dir: Path) -> ResumenTemas:
    """Lee todas las notas del directorio y agrega los temas."""
    resumen = ResumenTemas()
    for nota in sorted(notas_dir.glob("*.md")):
        try:
            texto = nota.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        resumen.notas_leidas += 1
        codigos, edad = extraer_de_nota(texto)
        if edad is not None:
            resumen.edades.append(edad)
        if not codigos:
            resumen.notas_sin_cie += 1
            continue
        for codigo in codigos:
            resumen.codigos[codigo] += 1
            resumen.capitulos[_capitulo(codigo)] += 1
        resumen.detalles.append(f"{nota.stem}: {', '.join(codigos)}")
    return resumen


def _bucket_edad(edad: int) -> str:
    if edad < 18:
        return "niñez / adolescencia (<18)"
    if edad < 60:
        return "adultos (18-59)"
    return "adultos mayores (60+)"


def resumen_markdown(resumen: ResumenTemas) -> str:
    """El 'tu mes en numeros' en markdown (para OneDrive/Telegram)."""
    lineas = ["# Tu mes en números", ""]
    lineas.append(f"Notas analizadas: **{resumen.notas_leidas}**")
    if resumen.con_edad():
        lineas.append(
            f"Pacientes con edad registrada: **{resumen.con_edad()}** "
            f"(adultos mayores: **{resumen.adulto_mayor()}**)"
        )
    lineas.append("")

    lineas.append("## Temas por capítulo CIE-10")
    if resumen.capitulos:
        total = sum(resumen.capitulos.values())
        for cap, n in resumen.capitulos.most_common():
            pct = round(100 * n / total)
            lineas.append(f"- **{cap}**: {n} ({pct}%)")
    else:
        lineas.append("- (sin diagnósticos con CIE-10 en las notas)")
    lineas.append("")

    lineas.append("## Diagnósticos más frecuentes")
    if resumen.codigos:
        for codigo, n in resumen.codigos.most_common(10):
            lineas.append(f"- **{codigo}** ({_capitulo(codigo)}): {n}")
    lineas.append("")

    if resumen.edades:
        buckets: Counter = Counter(_bucket_edad(e) for e in resumen.edades)
        lineas.append("## Edades")
        for bucket, n in buckets.most_common():
            lineas.append(f"- {bucket}: {n}")
        lineas.append(f"- Edad promedio: {sum(resumen.edades) // len(resumen.edades)} años")
        lineas.append("")

    if resumen.notas_sin_cie:
        lineas.append(
            f"({resumen.notas_sin_cie} notas sin código CIE-10 detectable)"
        )
    return "\n".join(lineas) + "\n"


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="temas",
        description="Resumen agregado de los temas que trata Yadira (REQ-083).",
    )
    parser.add_argument(
        "--notas-dir",
        type=Path,
        default=NOTAS_DIR,
        help="Directorio de notas clinicas (default: NOTAS_DIR de .env)",
    )
    parser.add_argument("--salida", type=Path, default=None, help="Markdown de salida")
    args = parser.parse_args(argv)

    resumen = analizar_notas(args.notas_dir)
    markdown = resumen_markdown(resumen)
    print(markdown)
    if args.salida:
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(markdown, encoding="utf-8")
        print(f"[temas] resumen guardado en: {args.salida}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
