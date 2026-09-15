# -*- coding: utf-8 -*-
"""Renombra Capitulo-*.pdf -> Capitulo-*.pdf (sin tilde precompuesta).

Trabaja con el nombre raw de Windows, que puede traer "i" + combining
acute (U+0301) en vez de "i" con tilde precompuesta (U+00ED).
"""
import os
import sys
import unicodedata

# Forzar stdout utf-8 (cp1252 rompe al imprimir el 'i' con tilde)
sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

SRC = r"C:\Workspace\Login-Automation\Manuales"


def normalize(name: str) -> str:
    """NFC para que 'i' + U+0301 -> 'i' con tilde precompuesta."""
    return unicodedata.normalize("NFC", name)


for raw_name in sorted(os.listdir(SRC)):
    if not raw_name.startswith("Cap") or not raw_name.endswith("-Web.pdf"):
        continue
    nfc = normalize(raw_name)
    if nfc == raw_name:
        continue
    new_name = nfc.replace("\u00ed", "i")  # 'i' con tilde -> 'i'
    old = os.path.join(SRC, raw_name)
    new = os.path.join(SRC, new_name)
    if os.path.exists(new):
        print(f"ya existe, skip: {new_name}")
        continue
    os.rename(old, new)
    print(f"renamed: {raw_name!r} -> {new_name}")
