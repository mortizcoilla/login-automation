"""Tests para _parsear_eventos_json (parser de opencode events)."""
from src.tools.generar_ficha_con_llm import _parsear_eventos_json


def test_un_solo_text_event():
    """Un step con un solo evento text devuelve su contenido."""
    sample = (
        '{"type":"step_start","timestamp":1787727471006}\n'
        '{"type":"text","text":"OK","time":{"start":1,"end":2}}\n'
        '{"type":"step_finish","reason":"stop"}'
    )
    assert _parsear_eventos_json(sample) == "OK"


def test_multiples_text_events_concatenados():
    """Multiples eventos text se concatenan en orden."""
    sample = (
        '{"type":"text","text":"Hola "}\n'
        '{"type":"text","text":"mundo"}\n'
        '{"type":"step_finish"}'
    )
    assert _parsear_eventos_json(sample) == "Hola mundo"


def test_assistant_message_con_content_list():
    """Mensaje assistant con content list se concatena correctamente."""
    sample = (
        '{"type":"assistant","message":{"content":['
        '{"type":"text","text":"Texto 1"},'
        '{"type":"text","text":" Texto 2"}'
        ']}}'
    )
    assert _parsear_eventos_json(sample) == "Texto 1 Texto 2"


def test_input_no_json_devuelve_crudo():
    """Si el input no es JSON, se devuelve el string crudo (fallback)."""
    sample = "Texto plano que no es JSON"
    assert _parsear_eventos_json(sample) == "Texto plano que no es JSON"


def test_json_invalido_entre_lineas_validas():
    """JSON invalido entre lineas validas se ignora, devuelve lo valido."""
    sample = (
        "esto no es json\n"
        '{"type":"text","text":"valido"}\n'
        "tampoco json"
    )
    assert _parsear_eventos_json(sample) == "valido"