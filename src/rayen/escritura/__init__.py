"""Capa de ESCRITURA sobre Rayen (opuesta a `src.rayen.extraccion`).

Hasta paso 7 (Mortadelo) el proyecto solo LEIA de Rayen. El paso 8
(cargar_ficha) necesita escribir la ficha generada de vuelta en Rayen.
Aca viven las funciones que toman el control del driver y manipulan
los campos de la UI de Rayen.

Conventions:
- Funciones reciben el `driver` ya posicionado en la ficha del
  paciente (post doble-click + carga del panel).
- Devuelven bool de exito o un objeto con detalle.
- NUNCA auto-envian: el proyecto respeta la regla dura de aprobacion
  humana de Yadira. Pegan texto y dejan a Yadira que revise/apriete
  Guardar.
"""
