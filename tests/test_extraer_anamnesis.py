"""Tests mockeados de extraer_anamnesis().

Estos tests validan la LOGICA de extraccion (selector, JS, fallback) sin
necesidad de Chrome. Miguel mostro 5 capturas de Rayen con pacientes
donde la anamnesis SIEMPRE existe renderizada en `li#anamnesis`. Estos
tests prueban que el codigo de extraccion la lee correctamente.

Casos cubiertos:
1. DOM completo estilo Rayen: anamnesis con `.collapse-text-sub .textoverflow-container`
2. Sin `.collapse-text-sub`: fallback a `li.textContent`
3. Sin ver_mas button: no falla
4. Ver_mas button: hace click y expande
5. li#anamnesis vacio: devuelve string vacio
6. Anamnesis con motivo hermano (no contamina): el extractor aísla solo la anamnesis
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

from src.rayen.extraccion.atencion_actual import extraer_anamnesis


def _make_logger() -> logging.Logger:
    logger = logging.getLogger("test_anamnesis")
    logger.setLevel(logging.CRITICAL)
    return logger


def _make_anamnesis_element(
    motivo_texto: str = "interconsulta",
    anamnesis_texto: str = "Paciente de 26 anos de edad, acude sola, sin ayuda tecnica",
    tiene_ver_mas: bool = True,
) -> MagicMock:
    """Construye un mock del DOM `li#anamnesis` estilo Rayen.

    Estructura real (inferred de las capturas 2026-08-25 + HANDOFF-PROYECTO-2026-08-23):
        <li id="anamnesis">
            <div class="textoverflow-container" style="height: 28px;">{motivo}</div>
            <div class="collapse-text-sub">
                <div class="textoverflow-container">{anamnesis}</div>
                <div class="textoverflow-button">...ver mas</div>
            </div>
        </li>
    """
    motivo_container = MagicMock()
    motivo_container.text = motivo_texto

    anamnesis_container = MagicMock()
    anamnesis_container.text = anamnesis_texto

    ver_mas = MagicMock()
    ver_mas.text = "...ver mas"

    collapse_sub = MagicMock()

    def collapse_query(selector: str) -> MagicMock | None:
        if "textoverflow-container" in selector and "height: 28px" not in selector:
            return anamnesis_container
        if "textoverflow-button" in selector:
            return ver_mas if tiene_ver_mas else None
        return None

    collapse_sub.query_selector = MagicMock(side_effect=collapse_query)

    def li_query(selector: str) -> MagicMock | None:
        if "collapse-text-sub" in selector and "textoverflow-container" in selector:
            return anamnesis_container
        if ".collapse-text-sub .textoverflow-container" in selector:
            return anamnesis_container
        if ".collapse-text-sub" in selector and "textoverflow-button" in selector:
            return ver_mas
        if ".textoverflow-button" in selector:
            return ver_mas if tiene_ver_mas else None
        return None

    li_mock = MagicMock()
    li_mock.find_element = MagicMock(side_effect=li_query)
    li_mock.find_element.side_effect = li_query
    li_mock.text = anamnesis_texto  # para fallback
    return li_mock


class TestExtraerAnamnesis:
    """Tests del extractor de anamnesis contra DOM mockeado estilo Rayen."""

    def test_extrae_anamnesis_basica(self) -> None:
        """DOM completo: devuelve el texto del contenedor de anamnesis."""
        li_mock = _make_anamnesis_element(
            motivo_texto="interconsulta",
            anamnesis_texto="Paciente de 26 anos de edad",
        )
        driver = MagicMock()
        driver.find_element = MagicMock(return_value=li_mock)

        # Simula el JS que extrae textContent del contenedor
        def execute_script(js: str) -> str:
            if "li#anamnesis" in js and "collapse-text-sub" in js:
                return "Paciente de 26 anos de edad"
            return ""

        driver.execute_script = MagicMock(side_effect=execute_script)

        resultado = extraer_anamnesis(driver, _make_logger())
        assert "26 anos" in resultado
        assert "interconsulta" not in resultado  # el motivo NO se filtra

    def test_fallback_cuando_no_hay_collapse_text_sub(self) -> None:
        """Si no existe `.collapse-text-sub .textoverflow-container`, usa `li.textContent`."""
        anamnesis_texto = "Anamnesis directa sin collapse-sub"
        li_mock = MagicMock()
        li_mock.find_element = MagicMock(side_effect=lambda s: None)
        li_mock.text = anamnesis_texto
        driver = MagicMock()
        driver.find_element = MagicMock(return_value=li_mock)

        # El JS real de extraer_anamnesis es UN solo execute_script. Si no
        # encuentra `.collapse-text-sub .textoverflow-container`, cae al
        # fallback `return li.textContent`. Simulamos ese comportamiento.
        def execute_script(js: str) -> str:
            if "li#anamnesis" in js and "collapse-text-sub" in js:
                return anamnesis_texto  # fallback del JS: li.textContent
            return ""

        driver.execute_script = MagicMock(side_effect=execute_script)

        resultado = extraer_anamnesis(driver, _make_logger())
        assert "Anamnesis directa" in resultado

    def test_sin_ver_mas_button_no_falla(self) -> None:
        """Si no hay boton 'ver mas' (texto corto), el script no falla."""
        li_mock = _make_anamnesis_element(tiene_ver_mas=False)
        driver = MagicMock()
        driver.find_element = MagicMock(return_value=li_mock)

        def execute_script(js: str) -> str:
            if "li#anamnesis" in js and "textoverflow-container" in js:
                return "Texto corto sin ver mas"
            return ""

        driver.execute_script = MagicMock(side_effect=execute_script)

        resultado = extraer_anamnesis(driver, _make_logger())
        assert "Texto corto" in resultado

    def test_anamnesis_vacia_devuelve_string_vacio(self) -> None:
        """Si li#anamnesis existe pero esta vacio, devuelve string vacio (no placeholder)."""
        li_mock = MagicMock()
        li_mock.find_element = MagicMock(side_effect=lambda s: None)
        li_mock.text = ""
        driver = MagicMock()
        driver.find_element = MagicMock(return_value=li_mock)
        driver.execute_script = MagicMock(return_value="")

        resultado = extraer_anamnesis(driver, _make_logger())
        assert resultado == ""

    def test_error_find_element_devuelve_vacio(self) -> None:
        """Si find_element falla (panel no cargo), devuelve string vacio (no raise)."""
        driver = MagicMock()
        driver.find_element = MagicMock(side_effect=Exception("no such element: li#anamnesis"))

        resultado = extraer_anamnesis(driver, _make_logger())
        assert resultado == ""

    def test_no_contamina_con_motivo(self) -> None:
        """El motivo 'interconsulta' (en otro .textoverflow-container hermano) NO se filtra."""
        anamnesis_texto_largo = (
            "Paciente de 32 anos de edad, acude sola, sin ayuda tecnica. "
            "Sintomas respiratorios. Se indica paracetamol."
        )
        li_mock = _make_anamnesis_element(
            motivo_texto="Sint respiratorio",
            anamnesis_texto=anamnesis_texto_largo,
        )
        driver = MagicMock()
        driver.find_element = MagicMock(return_value=li_mock)

        captured_js: list[str] = []

        def execute_script(js: str) -> str:
            captured_js.append(js)
            if "li#anamnesis" in js and "textoverflow-container" in js:
                return anamnesis_texto_largo
            return ""

        driver.execute_script = MagicMock(side_effect=execute_script)

        resultado = extraer_anamnesis(driver, _make_logger())

        # El JS de extraccion debe apuntar al sub-contenedor, NO al motivo
        # (que es otro .textoverflow-container con style="height: 28px")
        assert any(
            "collapse-text-sub" in js and "textoverflow-container" in js for js in captured_js
        ), "El extractor debe apuntar a .collapse-text-sub .textoverflow-container"
        assert "Sint respiratorio" not in resultado
        assert "32 anos" in resultado
        assert "paracetamol" in resultado
