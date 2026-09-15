"""Deteccion y extraccion del trigger `** mortadelo` en la nota clinica.

Yadira deja mensajes a Mortadelo dentro de la nota de Rayen con una marca
especial. Mortadelo los detecta, ejecuta la instruccion y los borra.

Regla de matching (regla dura, no se cambia sin autorizacion):
- La marca empieza con dos asteriscos: `**`
- Le sigue opcionalmente espacios en blanco
- Le sigue el nombre `Mortadelo` (case-insensitive: `mortadelo`,
  `Mortadelo`, `MORTADELO`, etc.)
- Despues del nombre, REQUERIDO uno de: whitespace, `:`, `;`, `-`, o
  fin de linea / fin de texto. NO matchea si despues viene `.` o `,`
  inmediatamente (eso indica que la marca no es un trigger completo).

Variantes validas:
- `** mortadelo`            (minusculas, con espacio)
- `**Mortadelo`             (nombre propio, sin espacio)
- `** MORTADELO`            (mayusculas, con espacio)
- `**mortadelo`             (todo minusculas, sin espacio)
- `**MORTADELO`             (mayusculas, sin espacio)
- `** Mortadelo`            (nombre propio, con espacio)
- `** mortadelo:`           (con `:` indicando instruccion)
- `**Mortadelo -`           (con `-` indicando instruccion)
- `  **  mortadelo  ...`    (espacios alrededor tolerados)

El trigger NO matchea:
- `**mortadelo` como parte de otra palabra (ej. `**mortadelox`)
- Una sola marca `*` (asterisco simple)
- `**mortadelo.` o `**mortadelo,` (puntuacion inmediata sin espacio)
- Variantes con guion o caracteres extra entre `**` y el nombre
"""
from __future__ import annotations

import re

# Regex case-insensitive. Captura el match entero (asteriscos + espacios
# + nombre) para poder borrarlo despues con `re.sub`.
# El lookahead al final requiere que despues del nombre venga un
# terminador valido (whitespace, `:`, `,`, `;`, `-`, o fin de linea/texto).
# Esto evita matchear `**mortadelo.` (punto inmediato) o como parte de
# otra palabra (`**mortadelox`). La coma se acepta porque Yadira
# efectivamente escribe `** Mortadelo, realiza...` (caso 2026-08-22,
# ficha Cecilia Reyes).
TRIGGER_RE: re.Pattern[str] = re.compile(
    r"\*\*\s*Mortadelo(?=[\s:,;\-]|$)",
    re.IGNORECASE | re.MULTILINE,
)


def contiene_trigger(nota: str) -> bool:
    """True si la nota contiene al menos un trigger de Mortadelo.

    Args:
        nota: texto completo de la nota clinica de Yadira en Rayen.

    Returns:
        True si hay al menos un match. False en caso contrario
        (nota vacia, sin trigger, o trigger mal formado).
    """
    if not nota:
        return False
    return bool(TRIGGER_RE.search(nota))


def extraer_triggers(nota: str) -> list[re.Match[str]]:
    """Devuelve la lista de matches del trigger en la nota, en orden.

    Util cuando Yadira deja varios mensajes en la misma nota.
    """
    if not nota:
        return []
    return list(TRIGGER_RE.finditer(nota))


def contar_triggers(nota: str) -> int:
    """Cuenta cuantos triggers hay en la nota."""
    if not nota:
        return 0
    return len(TRIGGER_RE.findall(nota))


__all__ = [
    "TRIGGER_RE",
    "contar_triggers",
    "contiene_trigger",
    "extraer_triggers",
]
