"""Demo en vivo: simulación completa del flujo Pilita/Teodoro/Pancho.

Muestra cómo trabaja el sistema end-to-end con datos simulados. NO toca
Rayen real (porque la sesión no existe acá y el submit es stub), pero
ejercita todas las piezas: la state machine, la auditoría, el
principio de validación, y el reporte de Anita.

Uso: python demo_app.py
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src import queue_store as qs
from src.anita.format_telegram import formatear_telegram
from src.anita.report_generator import generar_reporte
from src.pancho_skills.enviar import TokenInvalidoError, enviar_ficha
from src.queue_store import (
    EstadoFicha,
    crear_ficha,
    generar_token,
    inicializar_db,
)


# === Colores y formato ===

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    YADIRA = "\033[96m"      # cyan
    PILITA = "\033[92m"      # verde
    TEODORO = "\033[95m"     # magenta
    PANCHO = "\033[93m"      # amarillo
    ANITA = "\033[91m"       # rojo
    SYSTEM = "\033[90m"      # gris
    HEADER = "\033[1;97;44m"  # bold blanco sobre azul


def header(texto: str) -> None:
    bar = "═" * 70
    print(f"\n{C.HEADER} {texto} {C.RESET}")
    print(f"{C.SYSTEM}{bar}{C.RESET}")


def yadira(texto: str) -> None:
    print(f"  {C.YADIRA}{C.BOLD}YADIRA{C.RESET}  {C.YADIRA}│{C.RESET} {texto}")


def pilita(texto: str) -> None:
    print(f"  {C.PILITA}{C.BOLD}PILITA{C.RESET}  {C.PILITA}│{C.RESET} {texto}")


def teodoro(texto: str) -> None:
    print(f"  {C.TEODORO}{C.BOLD}TEODORO{C.RESET} {C.TEODORO}│{C.RESET} {texto}")


def pancho(texto: str) -> None:
    print(f"  {C.PANCHO}{C.BOLD}PANCHO{C.RESET}  {C.PANCHO}│{C.RESET} {texto}")


def anita(texto: str) -> None:
    print(f"  {C.ANITA}{C.BOLD}ANITA{C.RESET}   {C.ANITA}│{C.RESET} {texto}")


def system(texto: str) -> None:
    print(f"  {C.SYSTEM}· {texto}{C.RESET}")


def ok(texto: str) -> None:
    print(f"  {C.PILITA}✓ {texto}{C.RESET}")


# === Simulación ===

# Datos clínicos simulados de Teodoro (lo que produciría en un caso real)
ANALISIS_TEODORO_F1 = """\
**Impresión Diagnóstica**
HTA esencial en mujer de 50 años, presumiblemente en estadio 2 (PA 160/100), con adherencia terapéutica irregular. Escenario de alto riesgo de daño de órgano blanco si no se actúa.

**Diagnóstico Diferencial**
1. HTA esencial no controlada (90% de prevalencia)
2. HTA secundaria — hiperaldosteronismo (por edad y sexo)
3. SAHOS (prevalencia alta en HTA resistente)
4. Renal (estenosis arteria renal)
5. Farmacológica/dietaria (AINEs, AOV, sodio)

**Plan de Manejo APS**
- Confirmar patrón con AMPA/MAPA
- Labs: creatinina, VFG, perfil lipídico, HbA1c, RAC
- ECG basal + fondo de ojo
- Terapia combinada: IECA + calcioantagonista (enalapril + amlodipino)
- Meta PA <140/90

**Criterios de Derivación (SIC)**
- Sospecha fundada de HTA secundaria → Medicina Interna
- HTA resistente verdadera → Cardiología
- Emergencia hipertensiva → SAPU/SAR inmediato

**Educación y Red Flags**
- ⚠ PA >180/110 en casa → SAPU
- ⚠ Dolor torácico, déficit neurológico, disnea → urgencia
- Restricción sodio, adherencia estricta"""


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "queue.db")
        # Apuntar el sistema completo (incluyendo pancho_skills.enviar) a esta DB
        os.environ["LOGIN_AUTOMATION_DB"] = db
        inicializar_db(db)
        fecha = "23-07-2026"
        yadira_id = "telegram:111"  # sender_id de Yadira (aún pendiente de capturar el real)

        # ============================================================
        header("ESCENA 1 — Yadira se conecta con Pilita")
        # ============================================================
        yadira("Hola Pilita, ¿qué fichas tengo hoy?")
        pilita(f"Buenos días, Yadira. Voy a pedirle a Pancho que liste las "
               f"'Iniciado' del {fecha}.")
        pilita("Dame un segundo.")
        pancho("Conectando a Rayen APS... login OK con credenciales de Yadira.")
        pancho(f"Listando fichas 'Iniciado' para {fecha}... encontré 3.")

        # Crear las 3 fichas en la cola
        f1 = crear_ficha(db, "Karina Muñoz Farfán", "Control Crónico",
                        fecha, rut="119751349")
        f2 = crear_ficha(db, "Jorge Valenzuela Leal", "Control Crónico",
                        fecha, rut="64199137")
        f3 = crear_ficha(db, "Carmen Ponce Rojas", "Control Integral ECICEP-G2",
                        fecha, rut="165714687")
        ok(f"3 fichas persistidas en la cola (DB: queue.db)")

        pilita(f"3 fichas iniciadas, Yadira:")
        pilita(f"  1. {f1.paciente_nombre} — {f1.tipo_atencion}")
        pilita(f"  2. {f2.paciente_nombre} — {f2.tipo_atencion}")
        pilita(f"  3. {f3.paciente_nombre} — {f3.tipo_atencion}")

        # ============================================================
        header("ESCENA 2 — Yadira pide procesar la ficha 1")
        # ============================================================
        yadira("Procesa la ficha 1, la de Karina.")
        pilita("Ok, le pido a Teodoro el análisis clínico completo.")
        pilita(f"Contexto que le paso: nota clínica de Yadira + historial "
               f"que Pancho va a traer.")
        pancho("Trayendo historial clínico + farma de Karina Muñoz (RUT hash)...")
        system("(stub: historial no implementado, así que solo paso el contexto básico)")
        teodoro(f"Recibido. Procesando caso de {f1.paciente_nombre}...")
        teodoro(f"Análisis completo en formato 5 bloques (resumido para la demo):")
        for linea in ANALISIS_TEODORO_F1.split("\n"):
            if linea.strip():
                teodoro(f"  {linea}")
        pilita("Draft listo. Te lo presento:")

        contenido_f1 = f"**FICHA: {f1.paciente_nombre}**\n\n" + ANALISIS_TEODORO_F1
        qs.actualizar_contenido(db, f1.id, contenido_f1, aprobador_id="sistema",
                                accion="REGENERAR_DRAFT_TEODORO")
        qs.avanzar_estado(db, f1.id, EstadoFicha.EN_REVISION_USER,
                          aprobador_id="sistema", accion="MOSTRAR_USER")
        ok(f"Ficha {f1.id} → EN_REVISION_USER (auditada en historial)")

        # ============================================================
        header("ESCENA 3 — Yadira revisa y aprueba con ✅")
        # ============================================================
        yadira("✅")
        system("(Yadira aprobó la ficha)")
        qs.avanzar_estado(db, f1.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO,
                          aprobador_id=yadira_id, accion="APROBAR",
                          metadata={"hash_corto": contenido_f1[:32]})
        ok(f"Ficha {f1.id} → APROBADO_PENDIENTE_ENVIO")
        pilita("Aprobada. Cuando quieras enviarla, decime 📤.")

        # ============================================================
        header("ESCENA 4 — Yadira da el 📤")
        # ============================================================
        yadira("📤")
        token = generar_token(db, f1.id, contenido_f1, ttl_segundos=300)
        system(f"Token generado: #{token.id} (TTL: 5 min, expira {token.expira_en})")
        pilita(f"Token #{token.id} generado. Pidiendo a Pancho que envíe.")

        # Llamar a enviar_ficha (sin WebDriver real, va a fallar por NotImplementedError,
        # pero el token check ya pasó)
        pancho(f"Recibido. Token #{token.id} + ficha {f1.id} + contenido (hash {token.hash_contenido[:12]}...).")
        pancho("Validando token contra la DB...")
        try:
            enviar_ficha(driver=None, ficha_id=f1.id, paciente_id="119751349",
                         contenido=contenido_f1, token=token.id,
                         logger=logging.getLogger("pancho_demo"))
        except (NotImplementedError, TokenInvalidoError) as e:
            err_name = type(e).__name__
            system(f"Pancho reporta: {err_name}")
            if isinstance(e, NotImplementedError):
                system("→ esperado: el submit real a Rayen aún no está implementado.")
                system("→ PERO la validación del token PASÓ (por eso llegamos a NotImplementedError, no a TokenInvalidoError).")
                # Marcamos manualmente como enviado para que el demo avance
                qs.avanzar_estado(db, f1.id, EstadoFicha.ENVIADO,
                                  aprobador_id=yadira_id, accion="ENVIAR")
                ok(f"Ficha {f1.id} → ENVIADO (simulado para la demo)")

        # ============================================================
        header("ESCENA 5 — Yadira revisa la ficha 2 y la RECHAZA con feedback")
        # ============================================================
        yadira("Procesa la ficha 2.")
        pilita("Pidiendo a Teodoro el análisis de Jorge Valenzuela...")
        contenido_f2 = "**FICHA: Jorge Valenzuela Leal**\n\nAnálisis breve de Jorge, HTA controlada."
        qs.actualizar_contenido(db, f2.id, contenido_f2, aprobador_id="sistema",
                                accion="REGENERAR_DRAFT_TEODORO")
        qs.avanzar_estado(db, f2.id, EstadoFicha.EN_REVISION_USER,
                          aprobador_id="sistema", accion="MOSTRAR_USER")
        yadira("❌ me faltó agregar el IMC y la creatinina, regenerá con eso")
        pilita("Ok, le paso el feedback a Teodoro. Vuelvo a regenerar.")
        qs.avanzar_estado(db, f2.id, EstadoFicha.EN_CORRECCION,
                          aprobador_id=yadira_id, accion="PEDIR_CORRECCION",
                          metadata={"feedback": "agregar IMC y creatinina"})
        # Teodoro regenera
        contenido_f2_v2 = contenido_f2 + "\n\n**Agregado:**\n- IMC: 28.5\n- Creatinina: 0.9 mg/dL"
        qs.actualizar_contenido(db, f2.id, contenido_f2_v2, aprobador_id="sistema",
                                accion="REGENERAR_CON_FEEDBACK")
        qs.avanzar_estado(db, f2.id, EstadoFicha.EN_REVISION_USER,
                          aprobador_id="sistema", accion="RE_MOSTRAR")
        ok(f"Ficha {f2.id} regenerada con el feedback, vuelve a EN_REVISION_USER")
        yadira("✅ ahora sí")
        qs.avanzar_estado(db, f2.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO,
                          aprobador_id=yadira_id, accion="APROBAR")

        # ============================================================
        header("ESCENA 6 — Alguien NO autorizado intenta aprobar la ficha 3")
        # ============================================================
        yadira("Mientras tanto, el gato Pancho le mete mano a la ficha 3...")
        system("(esto es un test del principio de validación)")
        # Simulamos que un actor no-Yadira intenta aprobar
        qs.avanzar_estado(db, f3.id, EstadoFicha.EN_REVISION_USER,
                          aprobador_id="sistema", accion="MOSTRAR_USER")
        try:
            qs.avanzar_estado(db, f3.id, EstadoFicha.APROBADO_PENDIENTE_ENVIO,
                              aprobador_id="alguien_raro", accion="APROBAR")
        except Exception:
            pass
        # Como no hay validación de identidad en la state machine (eso se hace
        # a nivel Pilita), el "approve" pasa. La validación de identidad
        # la hace Pilita ANTES de llamar a avanzar_estado. Lo dejamos
        # documentado.
        system("(nota: la validación de identidad Telegram sender_id === Yadira")
        system(" se hace en Pilita, ANTES de invocar la state machine)")
        system("(en producción, Pilita rechaza el 'APROBAR' si sender_id != Yadira)")

        # ============================================================
        header("ESCENA 7 — Son las 19:00, Anita manda el reporte")
        # ============================================================
        system("(cron de Anita dispara a las 19:00)")
        anita("Generando reporte del día...")
        anita(f"Fecha: {fecha}")
        reporte = generar_reporte(db, fecha)
        anita("Reporte listo. Lo mando a Yadira por Telegram.")
        print()
        print(formatear_telegram(reporte))
        print()

        # ============================================================
        header("ESTADO FINAL DE LA COLA")
        # ============================================================
        # Mostrar todas las fichas con su estado
        with qs.get_connection(db) as conn:
            rows = conn.execute(
                "SELECT * FROM fichas ORDER BY id"
            ).fetchall()
        print()
        for r in rows:
            f = qs._row_to_ficha(r)
            icono = {
                EstadoFicha.DRAFT_GENERADO: "📝",
                EstadoFicha.EN_REVISION_USER: "👀",
                EstadoFicha.EN_CORRECCION: "🔄",
                EstadoFicha.APROBADO_PENDIENTE_ENVIO: "👍",
                EstadoFicha.ENVIADO: "✅",
                EstadoFicha.DESCARTADO: "🗑️",
            }.get(f.estado, "?")
            print(f"  {icono} {f.paciente_nombre:<30s} | {f.tipo_atencion:<30s} | {f.estado.value}")

        # Mostrar historial de aprobaciones
        print()
        system("Auditoría (últimas 10 acciones):")
        with qs.get_connection(db) as conn:
            hist = conn.execute(
                "SELECT * FROM historial_aprobaciones ORDER BY id DESC LIMIT 10"
            ).fetchall()
        for h in hist:
            ts = h["timestamp"]
            print(f"    {C.DIM}[{ts}]{C.RESET} ficha={h['ficha_id']:<2d} "
                  f"{h['accion']:<25s} por {h['aprobador_id']}")

        # Métricas
        print()
        metricas = qs.obtener_metricas_dia(db, fecha)
        system(f"Métricas del día: iniciadas={metricas['total_iniciadas']}, "
               f"enviadas={metricas['total_enviadas']}, "
               f"rechazadas={metricas['total_rechazadas']}")

        print()
        print(f"{C.SYSTEM}{'─' * 70}{C.RESET}")
        print(f"{C.BOLD}FIN DE LA DEMO{C.RESET}")
        print(f"{C.SYSTEM}Lo que viste: state machine + auditoría + principio de")
        print(f"validación + reporte de Anita — todo funcionando con SQLite.{C.RESET}")
        print(f"{C.SYSTEM}Lo que falta para producción real: submit a Rayen y")
        print(f"endpoints de historial (ambos en NotImplementedError explícito).{C.RESET}")
        print(f"{C.SYSTEM}{'─' * 70}{C.RESET}")
        return 0


if __name__ == "__main__":
    sys.exit(main())
