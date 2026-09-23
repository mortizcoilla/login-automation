"""Avisos Telegram del scheduler (paso 9, REQ-076).

Dos mensajes para Yadira alrededor de la cadena diaria:
  - INICIO: jugueton, rota por dia de semana (y entre semanas via el
    ordinal de la fecha, para que no caiga siempre el mismo).
  - FIN: resumen corto ("Listo mama, X fichas procesadas y guardadas"),
    con conteo real leido del resumen que Mortadelo escribe en el log.

Envio: HTTP directo al Bot API (sendMessage). NO pasa por el proceso del
bot en polling, asi el aviso nunca compite por getUpdates. Un fallo de
aviso (red, token, chat) se loggea y devuelve False: NUNCA afecta la
cadena diaria.

Los emojis son contenido del producto pedido por la usuaria; viven solo
en estos textos, no en la logica.
"""

from __future__ import annotations

import logging
import os
import re
from datetime import date
from pathlib import Path

import requests
from dotenv import load_dotenv

# Patron del proyecto (credentials, rutas, llm_cli): quien lee env del
# .env lo carga. Sin esto, un import directo de este modulo no ve el
# token/chat y los avisos se omiten en silencio.
load_dotenv()

logger = logging.getLogger(__name__)
_API = "https://api.telegram.org/bot{token}/sendMessage"
_TIMEOUT = 30

# Un mensaje por arranque, intercalados por dia de semana (0=lunes) y
# rotando entre las opciones segun el ordinal de la fecha.
MENSAJES_INICIO: dict[int, list[str]] = {
    0: [
        "💪 Hola mama! Lunes con todo: arrancué el turno de fichas 🩺 Voy paciente por paciente 📋",
        "🌸 Lunes y ya me puse el delantal digital, mama. Las fichas no se revisan solas 🤖✨",
    ],
    1: [
        "📋 Martes de fichas, mama! Ya estoy dentro, paciente por paciente 🩺💛",
        "🐣 Martes en punto! Sus fichas estan en buenas patitas, mama ✨",
    ],
    2: [
        "🌵 Miercolmita! Comencé el repaso de fichas, mama. Todo fluye ✨",
        "🧶 Miercoles y voy tejiendo la informacion de tus pacientes, mama 🩺💛",
    ],
    3: [
        "🚀 Jueves con energia, mama! Fichas en marcha 📋✨",
        "🌻 Jueves y ahí voy, mama: paciente por paciente, con cariño 🩺",
    ],
    4: [
        "🎉 Viernes, mama! Ultimo esfuerzo de la semana: fichas en marcha 📋💪",
        "🌷 Viernes de cierre, mama! Voy por las fichas para que descanses tranquila 💛",
    ],
    5: [
        "🐾 Sabadito y las fichas solitas... ya me pongo, mama ✨",
    ],
    6: [
        "☀️ Domingo, mama. Si estoy corriendo hoy es por encargo especial 📋💛",
    ],
}

MENSAJES_FIN_OK = [
    "✅ Listo mama! {x} fichas procesadas y guardadas. Que descanses 💛🌙",
    "💛 Misión cumplida, mama: {x} fichas listas. Todo peludito ✨",
    "🏁 Terminé, mama! {x} fichas procesadas y guardadas. Orgullosa de mi trabajo 🩺",
]

MENSAJES_FIN_FALLO = [
    "⚠️ Mama, terminé pero algo falló en el camino ({detalle}). Lo dejé anotado; cuando puedas revisas 🙏",
    "🥺 Mama, la cadena terminó con problemas: {detalle}. Quedó todo en el log, no te preocupes 🙏",
]

# Saludo matutino 8:00 L-V (REQ-080). Rubicita: tierna, con garra.
SALUDOS_MATINALES = [
    "🐈‍⬛ Miau! Buenos dias mama! Rubicita ya estiró las patas y afiló las "
    "garras... tranquila, hoy solo ronroneo fichas 💛",
    "🌅 Buenos dias mama! Pasé la noche velando el sofá... ahora toca cazar "
    "el dia juntas 🐾 Te deseo una jornada hermosa 💛",
    "🐱 Miau mama! Desayuné y estoy lista: te doy pata (con garra, como "
    "siempre) para que hoy sea un gran dia ✨",
    "😼 Rrrr... buenos dias mama! Si alguien te molesta hoy, avisame: saco "
    "las garras 🐾 Te deseo un dia liguito 💛",
    "🌞 Miau! A despertar mama! Te dejé un mordisquito de suerte en la "
    "almohada 🐈‍⬛ Ahora, ¡a volar! 💛",
    "🐾 Buenos dias mama! Bigotes listos, arenera limpia y paciencia "
    "recargada. Vamos con todo 😸",
    "🌙 Miau mama! Hoy el dia deberia seguir el hilo... y si se "
    "enreda, jalo de la pata contigo 🐾✨",
]

# Frases de portada para el conteo de fichas abiertas.
FRASES_FICHAS_ABIERTAS = [
    "🐈 Miau mama! Contando las presas del mes... te doy pata con garra 🐾",
    "📋 Rrrr... mision de conteo completada. Mira lo que hay que cazar "
    "hoy, mama 😼",
    "🐾 Mama, hojeé el mes con mis bigotes: esto es lo que hay 🐈",
    "🐱 Contando con garra y cariño, mama. He aqui el inventario felino 📋✨",
]

_RESUMEN_MORTADELO_RE = re.compile(
    r"\[mortadelo\] === Resumen: (\d+)/(\d+) pacientes completos ==="
)
_NOTAS_RE = re.compile(r"\[crear_notas\] Modo --todos: (\d+) pacientes del informe")


def elegir_mensaje(pool: list[str], fecha: date) -> str:
    """Elige del pool intercalando: el ordinal de la fecha reparte turnos."""
    return pool[fecha.toordinal() % len(pool)]


def armar_mensaje_inicio(ahora: date, n_pacientes: int | None) -> str:
    """Saludo jugueton del dia + cuantos pacientes trae la lista."""
    base = elegir_mensaje(MENSAJES_INICIO[ahora.weekday()], ahora)
    if n_pacientes is not None:
        plural = "paciente" if n_pacientes == 1 else "pacientes"
        base += f"\nVan {n_pacientes} {plural} en la lista de hoy 📋"
    return base


def _ultimo_match(path: Path, regex: re.Pattern[str]) -> tuple[int, ...] | None:
    """El ultimo grupo de matches del regex en el archivo (o None)."""
    try:
        contenido = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    matches = regex.findall(contenido)
    return tuple(int(x) for x in matches[-1]) if matches else None


def contar_fichas_del_log(log_path: Path) -> tuple[int, int, int] | None:
    """(ok, total, notas) del ultimo resumen en scheduler.log, o None."""
    resumen = _ultimo_match(log_path, _RESUMEN_MORTADELO_RE)
    notas = _ultimo_match(log_path, _NOTAS_RE)
    if resumen is None:
        return None
    ok, total = resumen
    n_notas = notas[0] if notas else 0
    return ok, total, n_notas


def armar_mensaje_fin(ok: bool, fichas_ok: int | None, paso_fallido: int = 0) -> str:
    """Resumen corto de cierre.

    paso_fallido: numero del paso donde truno la cadena (1..5); 0 si no
    fallo ninguno. fichas_ok=None -> sin dato del log, mensaje sobrio.
    """
    if ok:
        if fichas_ok is None:
            return "✅ Listo mama! La cadena diaria terminó bien 💛"
        return elegir_mensaje(MENSAJES_FIN_OK, date.today()).format(x=fichas_ok)
    detalle = f"se trunco en el paso {paso_fallido}/5" if paso_fallido else "con error"
    return MENSAJES_FIN_FALLO[date.today().toordinal() % len(MENSAJES_FIN_FALLO)].format(
        detalle=detalle
    )


def armar_saludo_matutino(ahora: date) -> str:
    """Saludo de inicio del dia (8:00 L-V, REQ-080)."""
    return elegir_mensaje(SALUDOS_MATINALES, ahora)


def armar_aviso_fichas_abiertas(
    total: int, distribucion: list[tuple[str, int]]
) -> str:
    """Conteo de fichas abiertas con su distribucion (REQ-080).

    Formato pedido por la usuaria, en bloque monoespaciado para que las
    columnas queden alineadas en Telegram.
    """
    lineas = [f"TOTAL FICHAS ABIERTAS:{total}", "Distribucion por tipo de atencion:"]
    for tipo, n in sorted(distribucion, key=lambda x: x[1], reverse=True):
        lineas.append(f"  {tipo}{' ' * max(1, 45 - len(tipo))}{n}")
    portada = elegir_mensaje(FRASES_FICHAS_ABIERTAS, date.today())
    return f"{portada}\n```{chr(10)}{chr(10).join(lineas)}{chr(10)}```"


def enviar(texto: str) -> bool:
    """Envia un mensaje a Yadira. Devuelve True si Telegram lo acepto."""
    token = os.getenv("TELEGRAM_BOT_TOKEN_RUBICITA", "").strip()
    chat = os.getenv("TELEGRAM_CHAT_AVISOS", "").strip()
    if not token or not chat:
        logger.warning("Aviso omitido: falta TELEGRAM_BOT_TOKEN_RUBICITA o TELEGRAM_CHAT_AVISOS")
        return False
    try:
        resp = requests.post(
            _API.format(token=token),
            json={"chat_id": chat, "text": texto},
            timeout=_TIMEOUT,
        )
        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("Aviso enviado a chat %s", chat)
            return True
        logger.warning("Telegram rechazo el aviso: HTTP %s: %s", resp.status_code, resp.text[:200])
        return False
    except requests.RequestException as e:
        logger.warning("Aviso no enviado (red): %s", e)
        return False
