# Skill bundle: examenes

## Proposito

Leer examenes adjuntos a la ficha clinica (fotos, PDFs) y entregar
los datos estructurados para que Mortadelo los use en su advice.

## Alcance

- **Detectar** adjuntos en la nota de Yadira
- **Leer** imagenes (OCR) o PDFs (extraccion de texto)
- **Interpretar** resultados basicos (no diagnosticos finales)
- **Entregar** dict con campos especificos por tipo de examen

## Estado

**Stub.** Hoy: descripciones hardcoded por nombre de archivo.
Manana: OCR + vision LLM local.

## Tipos soportados (futuro)

| Tipo | Estado |
|---|---|
| audiometria | Stub (datos de Cecilia hardcoded) |
| ECG | Pendiente |
| laboratorio | Pendiente |
| imagen (Rx, etc.) | Pendiente |
| DICOM | No soportado |

## Privacidad

Los examenes contienen PII. La lectura es 100% local. Ver
`reglas.md` Regla 0.

## Integracion

El output se integra al bloque `** Mortadelo ->` del bundle activo.
Por ejemplo, en skill_morbilidad:

```
** Mortadelo -> Doctora:
  ...
  [EXAMEN ADJUNTO: AUDIOMETRIA 10-07-2026]
    - OD: 64%, OI: 84%
    - Conclusion: hipoacusia bilateral
  ...
```
