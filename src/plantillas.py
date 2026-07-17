import os
import re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLANTILLAS_DIR = os.path.join(BASE_DIR, "plantillas")
COMPLETADAS_DIR = os.path.join(PLANTILLAS_DIR, "completadas")


TIPOS_ATENCION = [
    "Morbilidad Telefónica",
    "Morbilidad Presencial",
    "Control Integral Multimorbilidad G3",
    "Control Integral Multimorbilidad G2",
    "Control Cronico DESCOMPENSADO",
    "Morbilidad",
    "Control Integral Multimorbilidad G1",
    "Ingreso Salud Mental Infantil",
    "Ingreso Multimorbilidad G3",
    "Control Integral ECICEP-G3",
    "Recetas",
    "Control Integral ECICEP-G2",
    "Ingreso Integral ECICEP-G3",
    "Control Salud",
    "Ingreso Multimorbilidad G2",
    "Control Integral ECICEP-G1",
    "Control Crónico",
    "Control Salud Mental Infantil",
    "Ingreso Integral ECICEP-G2",
    "Consultorías Adulto",
    "Seguimiento a distancia Multimorbilidad G2",
    "Consultoria salud Mental (Sesiones)",
    "Ingreso Integral ECICEP-G1",
    "Gestion Administrativa",
    "Consulta Salud Mental",
]


def sanitizar_tipo(tipo_atencion):
    return re.sub(r"^ME,\s*", "", tipo_atencion).strip()


def cargar_plantilla(tipo_atencion):
    tipo = sanitizar_tipo(tipo_atencion)
    ruta = os.path.join(PLANTILLAS_DIR, f"{tipo}.txt")
    if not os.path.exists(ruta):
        return None
    with open(ruta, "r", encoding="utf-8") as f:
        return f.read()


def rellenar_plantilla(texto, datos):
    hoy = datetime.now().strftime("%d-%m-%Y")
    reemplazos = {
        "{PACIENTE}": datos.get("nombre", ""),
        "{RUT}": datos.get("rut", ""),
        "{FECHA}": datos.get("fecha", hoy),
        "{RAZON}": datos.get("razon", ""),
        "{TIPO_ATENCION}": sanitizar_tipo(datos.get("tipo_atencion", "")),
        "{OBSERVACION}": datos.get("observacion", ""),
        "{HORA}": datos.get("hora", ""),
    }
    for placeholder, valor in reemplazos.items():
        texto = texto.replace(placeholder, valor)
    return texto


def guardar_plantilla(texto, nombre_paciente):
    os.makedirs(COMPLETADAS_DIR, exist_ok=True)
    hoy = datetime.now().strftime("%Y%m%d")
    nombre_archivo = f"{nombre_paciente}_{hoy}.txt"
    ruta = os.path.join(COMPLETADAS_DIR, nombre_archivo)
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(texto)
    return ruta
