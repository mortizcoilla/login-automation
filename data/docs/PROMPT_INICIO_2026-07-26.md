# Prompt de inicio — sesión 2026-07-26 (mañana)

Pega este prompt en una conversación nueva con Mavis para retomar el
proyecto Login-Automation desde donde quedamos.

---

```
Hola, vamos a retomar el proyecto Login-Automation.

Por favor primero lee completo el archivo
C:\Workspace\Login-Automation\docs\HANDOFF.md

Ahí está el kick off al cierre del 25-07-2026 + actualización del
26-07 madrugada con todo lo que construimos:

- 5 agentes Mavis (Pilita, Teodoro, Pancho, Gustavo, MORTADELO 🐱 nuevo)
- 9 scripts de análisis en src/analysis/ (incluyendo informe_fichas_abiertas.py nuevo)
- 3 DBs SQLite (fichas_completo, tracking, tracking_completo)
- Mortadelo con 6 manuales MINSAL cargados (HTA, DM2, Depresión, EPOC,
  IRA/ERA, PSCV, Ley 20.584, CIE-10)
- 4 fichas de prueba de Mortadelo validadas por Yadira en
  data/mortadelo/ (Sandra, Samuel, Héctor, Gloria)
- Regla de interconsulta validada: solo si la nota tiene
  `** realizar interconsulta` (en cualquier parte)

Lo que está PENDIENTE (orden de prioridad):
1. Sesión con Rayen abierto (~2-3 h) para cerrar:
   - Doble click sobre el nombre del paciente (cierra placeholder de leer_ficha)
   - Tab "Atención actual" (donde se pega la nota)
   - Conectar fecha de nacimiento del #1 (ya está visible en
     sección "Identificación" de la foto de Sandra/Samuel)
   - Derogar formalmente enviar_ficha (ya no se usa)
2. Rescatar año 2025 (20-40 min, sin Rayen)
3. Cron real en mini PC Ubuntu para actualizar_mes_actual
4. Análisis estadísticos sobre la DB completa
5. Implementar skills de Mortadelo 2, 3, 6, 7 (las que requieren Rayen)
6. Análisis pendiente: indicador de retraso cita vs llegada (registrado
   en mi memoria, va a la fase de informes)
7. Crear gatos restantes (Pelusa, Anita, los 5 del novio, posibles
   especialistas por categoría)
8. UI "Sala del CESFAM"
9. Debug Pilotabot Telegram
10. Limpiar código legacy (queue_store, enviar_ficha stub, queue.db)

Reglas duras (válidas al 26-07):
- SOLO validación humana: Yadira abre Rayen y cierra ella misma
- La marca `** realizar interconsulta` en la nota de Yadira es la
  ÚNICA señal para que Mortadelo incluya bloque de SIC. Es instrucción
  interna, NO debe aparecer en la ficha rellenada
- Ley 20.584: RUT nunca en DB de trabajo, header confidencial en
  exports fuera del sistema
- LLMs cloud OK, canales externos los decide Yadira

No re-compartir en chat los archivos sensibles (config/users.json,
config/api_config.json, data/raw_responses/*, data/pacientes_2026.csv,
data/analysis/*.db, data/analysis/*.txt, data/mortadelo/*.txt).

Sigo: Miguel, ingeniero, esposo de Yadira. Español de Chile.

Última conversación que cerramos (sábado 25-07 noche → domingo
26-07 madrugada): probamos a Mortadelo con 4 fichas. Las 3 con la
marca de interconsulta funcionaron, la que NO tenía marca (Gloria)
no incluyó SIC, y la marca se detectó tanto al inicio como al final
de la nota. La regla quedó validada.

Próximo paso prioritario: #1 (sesión con Rayen abierto) — me avisas
cuándo podemos hacerla y te llevo paso a paso.
```

---

## Cómo usar este prompt

1. Abrir nueva conversación con Mavis (sesión nueva)
2. Pegar el bloque de arriba (entre los ```)
3. Mavis lee el HANDOFF, te confirma lo que entendió, y te pregunta por dónde
4. Vos le decís "vamos con el #1" (o lo que decidas) y arrancan

## Si querés cambiar el orden

Reemplazá la última línea por el #N que prefieras. Por ejemplo:
- "Próximo paso: #2 (rescatar 2025)" → 20-40 min de script standalone
- "Próximo paso: #4 (análisis estadísticos)" → depende del alcance
- "Próximo paso: #7 (crear gato X)" → primero definimos qué hace
