"""Flujos reutilizables sobre la capa Selenium de Rayen.

Un "flujo" es una secuencia de operaciones de varios modulos de
`src.rayen.*` (navegacion, tabla, extraccion) que cumple un objetivo
funcional concreto, compartido entre pasos del pipeline.

Ejemplos:
- `apertura_ficha`: dado un paciente del informe, navegar a su fecha,
  buscarlo por nombre y abrir su ficha en Rayen. Hoy lo usan paso 3
  (Pancho / crear_notas_clinicas) y paso 8 (cargar_ficha).
"""
