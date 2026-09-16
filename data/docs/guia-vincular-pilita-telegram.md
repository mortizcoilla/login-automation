# Guía: Vincular Pilita a Telegram

> **Versión**: 1.0 — 2026-07-23
> **Para**: Médica CESFAM San Bernardo (usuaria del proyecto Login-Automation)
> **Alcance**: cómo conectar al equipo de agentes Mavis con tu Telegram

---

## El principio clave (léeme antes)

**Solo Pilita habla contigo por Telegram.** Los otros 11 gatos son internos: Pilita los invoca cuando los necesita.

Razón: si tuvieras 11 "contactos" en Telegram, tendrías que saber a quién llamar para cada cosa. Con un solo canal (Pilita), ella se encarga de:

- Si necesitas análisis clínico → Pilita llama a Teodoro
- Si necesitas algo en Rayen → Pilita llama a Pancho
- Si tenías una duda de salud mental → Pilita llama a Pelusa
- Si era una duda de fármacos → Pilita llama a Gustavo
- Si quieres el reporte del día → Pilita llama a Anita

Tú siempre hablas con Pilita. Ella hace el ruteo interno. Es más simple, más seguro (solo una superficie expuesta), y te permite agregar/quitar especialistas sin tocar Telegram.

**Excepción**: si más adelante quieres un canal directo con algún especialista (ej: una "línea de emergencia con Pelusa" para riesgo suicida), se puede agregar como una segunda ruta. Por ahora, Pilita es la cara visible.

---

## Prerequisitos (verifica antes de seguir)

1. ✅ Telegram ya está conectado a Mavis (dijiste que lo tienes configurado)
2. ✅ Mavis Mobile instalado en tu celular
3. ✅ Los 3 agentes ya están creados en disco:
   - `C:\Users\morti\.minimax\agents\pilita\`
   - `C:\Users\morti\.minimax\agents\teodoro\`
   - `C:\Users\morti\.minimax\agents\pancho\`
4. ⏳ La ruta IM Telegram → Pilita (lo que vamos a hacer)

---

## Paso 1 — Averigua tu chat-id y sender-id de Telegram

Necesitas 2 identificadores para crear la ruta:

| ID | Qué es | Cómo obtenerlo |
|---|---|---|
| **chat-id** | ID del chat entre tú y el bot | Lo entrega Mavis al primer mensaje; o lo pides al bot con `/start` |
| **sender-id** | Tu user ID de Telegram | Lo entrega Mavis en el log del primer mensaje; o lo pides a @userinfobot en Telegram |

**Procedimiento más simple** (no requiere CLI):

1. Abre Mavis Mobile
2. Anda al canal de Telegram ya conectado
3. Envíale un mensaje al bot (ej: "hola")
4. Mavis te mostrará un log con los IDs del mensaje entrante
5. Anota `chat_id` y `sender_id` (son números tipo `123456789`)

**Alternativa CLI** (si tienes el `mavis` CLI accesible):

```bash
mavis im status
mavis im route list --platform telegram
```

Esto te muestra el estado actual y los IDs de chats que ya están siendo ruteados.

---

## Paso 2 — Crea la ruta Pilita → Telegram

Una vez que tengas tu `chat-id` y `sender-id`, corre este comando:

```bash
mavis im route add \
  --id pilita-telegram \
  --platform telegram \
  --agent pilita \
  --chat-type p2p \
  --chat-id <TU_CHAT_ID> \
  --sender-id <TU_SENDER_ID> \
  --strategy per-chat \
  --priority 1
```

### Qué hace cada flag

| Flag | Valor | Por qué |
|---|---|---|
| `--id` | `pilita-telegram` | Identificador único de la regla (kebab-case) |
| `--platform` | `telegram` | Plataforma de IM |
| `--agent` | `pilita` | El agente que recibe los mensajes |
| `--chat-type` | `p2p` | Mensajes directos (1 a 1, no grupo) |
| `--chat-id` | tu número | Restringe a tu chat específico |
| `--sender-id` | tu número | Restringe a que SOLO TÚ puedas escribirle a Pilita (seguridad) |
| `--strategy` | `per-chat` | Una sesión por chat (cada chat con Pilita = sesión propia) |
| `--priority` | `1` | La más alta, para que no haya otra regla que la pise |

**Por qué `--sender-id` es importante**: sin este flag, cualquier persona que escriba a tu bot terminaría hablándole a Pilita (y por extensión, podría ver historiales clínicos). Con `--sender-id`, solo tú puedes. Esto es parte de la regla dura de privacidad.

---

## Paso 3 — Verifica la ruta

```bash
mavis im route get pilita-telegram
```

Deberías ver:
- `enabled: true`
- `agent: pilita`
- Los IDs correctos
- `strategy: per-chat`

Si la regla aparece bien, está lista.

---

## Paso 4 — Test de humo (sin datos clínicos)

Abre Telegram y habla con tu bot. Prueba esta conversación:

```
Tú:  hola

Pilita: Hola, soy Pilita. Soy la orquestadora del equipo del CESFAM.
        No tomo decisiones clínicas; mi trabajo es traerte la información
        y los análisis, y esperar tu OK antes de cualquier envío a Rayen.
        ¿En qué te ayudo?
```

Si responde, **la ruta funciona**. Si no responde, ve a Troubleshooting.

**Tests adicionales** (siguen siendo sin datos clínicos):

```
Tú:  qué gatos componen el equipo?

Pilita: El equipo está formado por 11 gatos médicos.
        Los que pueden activarse en el flujo principal son:
        - Yo, Pilita (orquestadora)
        - Teodoro (médico de familia APS)
        - Pancho (enfermero de proceso Rayen)
        Y si los necesitas para consulta:
        - Pelusa (salud mental)
        - Gustavo (farma)
        - Anita (reportes)
        - Luffyalberto, Dominga, Negrita, Mauricia, Rubí
        (estos últimos 5 aún no están creados; los sumamos cuando
         el MVP esté afinado)
```

```
Tú:  simula un caso: paciente 50a, HTA descompensada, dame el análisis
     de Teodoro sin llamar a Rayen

Pilita: Ok, le pido a Teodoro un análisis en seco.
        [Llama a Teodoro con contexto simulado]
        [Teodoro responde con los 5 bloques]
        Pilita: acá tienes el análisis de Teodoro...
```

**Si estos tests pasan, la integración está OK**. Pasamos a la siguiente fase.

---

## Paso 5 — Registrar evidencia (auditoría de configuración)

Una vez que la ruta esté funcionando, ejecuta:

```bash
mavis im route list --platform telegram
```

Guarda el output. Eso te sirve como:
- Comprobante de que la ruta existe
- Referencia para regenerar si algo se rompe
- Auditoría de qué agente está expuesto y a quién

Si más adelante agregas más agentes o quieres un canal directo con un especialista, repites el flujo.

---

## Troubleshooting

### El bot no responde en Telegram

| Síntoma | Causa probable | Solución |
|---|---|---|
| Bot silencioso, ningún mensaje | La ruta no se creó o el chat-id es incorrecto | `mavis im route get pilita-telegram` y revisa los IDs |
| Bot responde con error "agent not found" | Pilita no existe (raro, pero pasa si se borró) | Verifica con `mavis agent list | grep pilita` |
| Bot responde pero a nombre de otro agente | Conflicto de prioridades entre rutas | Revisa con `mavis im route list` y reordena `--priority` |
| Bot responde, pero Pilita dice que no puede invocar a Teodoro | Teodoro no está corriendo o no es accesible | `mavis agent get teodoro` y verifica que existe |

### Quiero hablar directo con Teodoro o Pancho (sin pasar por Pilita)

No es la práctica recomendada, pero se puede:

```bash
mavis im route add \
  --id teodoro-directo \
  --platform telegram \
  --agent teodoro \
  --chat-type p2p \
  --chat-id <chat_id_distinto> \
  --sender-id <tu_sender_id> \
  --strategy per-chat
```

Necesitas un chat-id distinto (otro bot de Telegram, o un grupo donde menciones a Teodoro). El detalle: para tener varios chats con distintos agentes, lo más limpio es crear un bot de Telegram por agente. Si quieres eso, hablamos.

### Mensajes caen en el agente equivocado

Si llegan mensajes al agente incorrecto:

```bash
mavis im route test \
  --platform telegram \
  --chat-type p2p \
  --chat-id <chat_id> \
  --sender-id <sender_id>
```

Esto hace un dry-run y te dice qué regla aplicaría. Si aplica la equivocada, ajusta `--priority` o `--chat-id`/`--sender-id` de la regla conflictiva.

---

## Cómo deshabilitar la ruta temporalmente

Si quieres pausar la integración (ej: mientras haces mantenimiento):

```bash
mavis im route update pilita-telegram --disabled
```

Para reactivar:

```bash
mavis im route update pilita-telegram --enabled
```

---

## Resumen del flujo esperado

```
Tú (Telegram) ──mensaje──> Bot de Telegram
                                │
                                ▼
                       Bridge IM de Mavis
                                │
                  [Aplica regla pilita-telegram]
                                │
                                ▼
                          Pilita
                                │
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
         Teodoro            Pancho            Pilita misma
       (análisis)         (procesos)         (orquesta y decide)
                                │
                                ▼
                          Tú (Telegram) ←respuesta de Pilita
```

Tú siempre hablas con Pilita. Pilita te muestra los análisis de Teodoro y los resultados de Pancho. La médica es la única que aprueba el envío final.

---

## Próximo paso

Una vez que la ruta esté funcionando y los tests de humo pasen, lo que sigue es:
1. Crear un caso de prueba con datos seudonimizados (no reales)
2. Pasarlo por el flujo Pilita → Teodoro → Pancho (sin enviar a Rayen)
3. Validar la state machine y los warnings
4. Cuando esté estable, primera ficha real

---

**¿Dudas con algún paso?** Si te trabas en algún comando, mándame el output y lo destrabamos.
