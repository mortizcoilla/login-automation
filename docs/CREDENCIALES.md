# Credenciales y API keys — Login-Automation

**Regla suprema:** las credenciales NUNCA se commitean al repo. Este documento NO contiene valores, solo la política y la ubicación.

---

## Ubicación de los secretos

| Secreto | Ubicación | En .gitignore | Notas |
|---|---|---|---|
| API keys LLM (OpenCode Go, MiniMax, Kimi) | `.env` (raíz del proyecto) | ✅ (`.env`, `.env.local`, `.env.*.local`) | No commitear. Rotar en panel del provider. |
| Credenciales Yadira (Rayen) | `config/users.json` | ✅ | Usuario + password de Yadira. Cambiar periódicamente. |
| Cookie de sesión Rayen | `config/api_config.json` | ✅ (desde 2026-08-23) | Cookie AspNet. Se regenera al hacer login. No persistir. |
| Cookies/headers HTTP efímeros | `config/api_config.local.json` | ✅ | Override local. Nunca commitear. |

**Verificación rápida** (qué se va a github):

```bash
git check-ignore -v .env config/users.json config/api_config.json
# Los 3 deben aparecer como "matched" (= no se suben).
```

---

## API keys de LLM — variables de entorno

Las 3 keys que dejó Miguel viven en `.env` con estos nombres:

| Variable | Provider | Modelos asociados |
|---|---|---|
| `OPENCODE_GO_API_KEY` | OpenCode Go (plan $5/mes) | `opencode-go/minimax-m3`, `opencode-go/kimi-k3`, `opencode-go/qwen3.8-max`, `opencode-go/glm-5.3`, `opencode-go/grok-4.5`, etc. |
| `MINIMAX_API_KEY` | MiniMax (directo) | `minimax/...` (no usado por default; opencode-go da acceso equivalente) |
| `KIMI_API_KEY` | Kimi / Moonshot (directo) | `kimi/kimi-k3`, `kimi/kimi-k2.7-code` |
| `GEMINI_API_KEY` | Google Gemini (directo) | `gemini-2.5-pro`, `gemini-3.1-pro-preview`, `gemini-2.5-flash` (vision). Usado como respaldo para vision si opencode da problemas. |

**Default del script:** `opencode-go/minimax-m3` para texto, `google/gemini-2.5-pro` (vía opencode) para vision/OCR de examenes.

**Cómo se usan:**

1. **OpenCode Go (recomendado):** `opencode` ya está autenticado vía `opencode auth login` en el user de Miguel. La key de `.env` es respaldo. El script `src/tools/generar_ficha_con_llm.py` invoca `opencode run --model opencode-go/<modelo> --agent mortadelo`.

2. **MiniMax o Kimi directos:** solo si se quiere saltar opencode. Requeriría refactor del script para llamar a la API del provider directo con `requests`. Por ahora NO se usa; opencode-go ya da acceso a esos modelos.

---

## Política de seguridad

1. **NUNCA commitear secretos.** Verificar con `git diff --staged` antes de cada `git commit`. Si una key se filtró, rotarla INMEDIATAMENTE en el panel del provider.

2. **NUNCA pegar keys en chat** (ni en issues, ni en logs, ni en responses de LLM). El script `generar_ficha_con_llm.py` NO loguea las keys.

3. **`.env` es local de Miguel.** Si Miguel clona el proyecto en otra máquina, debe regenerar las keys en los panels correspondientes y crear su propio `.env`.

4. **Rotación:**
   - Si una key se compromete: rotar en el panel del provider (opencode.ai/auth, platform.minimax.io, platform.moonshot.cn).
   - Actualizar `.env`.
   - NO commitear el cambio (el archivo ya está en .gitignore).

5. **Tracking histórico:** al 2026-08-23, `config/users.json` y `config/api_config.json` estaban tracked en git. Ya fueron removidos del tracking con `git rm --cached` y agregados a `.gitignore`. Los archivos quedan en disco local, pero NO se vuelven a commitear. **Si el repo está en github público, las keys históricas pueden estar expuestas — rotar de todas formas como medida de precaución.**

---

## Cómo rotar una key

```bash
# 1. Generar nueva key en el panel del provider
# 2. Editar .env local (no commitear)
# 3. Si opencode estaba autenticado con la key vieja, re-autenticar:
opencode auth login --provider <provider>
# 4. Borrar .env.old si quedó
# 5. Si la key estaba en github, hacer git filter-branch o BFG para limpiarla del historial
```

---

## Quién tiene acceso

Solo Miguel (Windows user `morti`) tiene el `.env` local. El proyecto es privado; no hay otros contribuidores con acceso al repo ni a las keys.

Si en el futuro Yadira (o el equipo) necesita acceso a las keys:
- NO se le pasa el `.env` por email/chat.
- Se crea un canal seguro (1Password, Bitwarden, o similar).
- Yadira autentica opencode con su propio `opencode auth login`.
