"""Scheduler del flujo diario (REQ-060).

Modulo aislado: no modifica nada preexistente. Componentes:
  - calendario.py: carga config/calendario.json y decide que vence ahora.
  - runner.py: ejecuta la cadena 4->5->3->6->7 por doctor y lleva estado.
  - instalar.py: registra/elimina la tarea de Windows (cada 30 min).

La tarea de Windows dispara cada 30 minutos; el modulo decide con el
calendario si corresponde correr. Asi el calendario vive SOLO en
config/calendario.json (cambiar horarios o agregar un doctor no toca el
Programador de Tareas), y si el PC estaba apagado a la hora programada,
corre en el primer disparo posterior.
"""
