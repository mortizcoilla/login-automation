"""Normalizacion de nombres de pacientes y convenciones de filename.

Hay DOS convenciones de filename en el proyecto, y son intencionalmente
distintas (REQ-012 vs REQ-002/027/028):

1. nombre_a_filename (examenes crudos): lowercase, SIN tildes, espacios a '_'.
   Ej. 'Lucia Adela Zambrano' -> 'lucia_adela_zambrano'.
2. safe_filename (notas/info/anam): conserva mayusculas y tildes (legible
   para Yadira), solo limpia caracteres no-word y espacios a '_'.
   Ej. 'Nicolás Ignacio Piña' -> 'Nicolás_Ignacio_Piña' (tilde conservada).

normalizar_texto: lowercase + sin tildes + espacios colapsados. Es la base
del matching por tokens (REQ-016) y de la convencion 1.
"""

from __future__ import annotations

import re
import unicodedata


def normalizar_texto(texto: str) -> str:
    """Quita tildes, pasa a minusculas, colapsa espacios/guiones bajos."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"[\s_]+", " ", sin_tildes).strip().lower()


def nombre_a_filename(nombre: str) -> str:
    """Convencion EXAMENES CRUDOS (REQ-012): lowercase, sin tildes, '_' entre
    palabras. Ej. 'Benedicto Alfonso Martin' -> 'benedicto_alfonso_martin'."""
    return re.sub(r"\s+", "_", normalizar_texto(nombre))


def safe_filename(nombre: str) -> str:
    """Convencion NOTAS/INFO/ANAM (REQ-002/027/028): conserva mayusculas y
    tildes. Quita chars no [\\w\\s-] y espacios a '_'.

    Ej. 'Eduardo Alfonso Serrano Carmona' -> 'Eduardo_Alfonso_Serrano_Carmona'.
    """
    out = re.sub(r"[^\w\s\-]+", "", nombre, flags=re.UNICODE)
    out = re.sub(r"\s+", "_", out.strip())
    return out
