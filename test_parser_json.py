"""Test rapido del parser JSON de opencode events."""
import sys
sys.path.insert(0, ".")
from src.tools.generar_ficha_con_llm import _parsear_eventos_json

# Caso 1: un solo text event
sample1 = (
    '{"type":"step_start","timestamp":1787727471006}\n'
    '{"type":"text","text":"OK","time":{"start":1,"end":2}}\n'
    '{"type":"step_finish","reason":"stop"}'
)
out1 = _parsear_eventos_json(sample1)
print("Caso 1 (1 text event):", repr(out1))
assert out1 == "OK", f"expected 'OK', got {out1!r}"

# Caso 2: multiples text events (como una respuesta larga del LLM)
sample2 = (
    '{"type":"text","text":"Hola "}\n'
    '{"type":"text","text":"mundo"}\n'
    '{"type":"step_finish"}'
)
out2 = _parsear_eventos_json(sample2)
print("Caso 2 (2 text events):", repr(out2))
assert out2 == "Hola mundo", f"expected 'Hola mundo', got {out2!r}"

# Caso 3: assistant message con content list (formato alternativo)
sample3 = (
    '{"type":"assistant","message":{"content":['
    '{"type":"text","text":"Texto 1"},'
    '{"type":"text","text":" Texto 2"}'
    ']}}'
)
out3 = _parsear_eventos_json(sample3)
print("Caso 3 (assistant content list):", repr(out3))
assert out3 == "Texto 1 Texto 2", f"expected 'Texto 1 Texto 2', got {out3!r}"

# Caso 4: input no es JSON (fallback: devolver el string crudo)
sample4 = "Texto plano que no es JSON"
out4 = _parsear_eventos_json(sample4)
print("Caso 4 (no JSON):", repr(out4))
assert out4 == "Texto plano que no es JSON", f"expected raw, got {out4!r}"

# Caso 5: JSON invalido entre lineas validas
sample5 = (
    "esto no es json\n"
    '{"type":"text","text":"valido"}\n'
    "tampoco json"
)
out5 = _parsear_eventos_json(sample5)
print("Caso 5 (mezcla):", repr(out5))
assert out5 == "valido", f"expected 'valido', got {out5!r}"

print("\n=== TODOS LOS TESTS PASARON ===")
