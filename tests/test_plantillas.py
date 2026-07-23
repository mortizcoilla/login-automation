from __future__ import annotations

from src.plantillas import sanitizar_tipo


def test_sin_prefijo() -> None:
    assert sanitizar_tipo("Control Crónico") == "Control Crónico"


def test_prefijo_me() -> None:
    assert sanitizar_tipo("ME, Control Crónico") == "Control Crónico"


def test_prefijo_me_espacio() -> None:
    assert sanitizar_tipo("ME,Control Crónico") == "Control Crónico"


def test_prefijo_en() -> None:
    assert sanitizar_tipo("EN, Morbilidad") == "Morbilidad"


def test_prefijo_minuscula() -> None:
    assert sanitizar_tipo("me, algo") == "algo"


def test_vacio() -> None:
    assert sanitizar_tipo("") == ""


def test_none_seguro() -> None:
    assert sanitizar_tipo("") == ""


def test_espacios_alrededor() -> None:
    assert sanitizar_tipo("  ME,  Test  ") == "Test"
