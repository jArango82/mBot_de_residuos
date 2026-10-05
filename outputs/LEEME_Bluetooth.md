# Control del mBot Ranger por Bluetooth

Robot actual: Makeblock_LE10a56219eb91 (verificado el 29 de septiembre). El módulo anterior se anunciaba como Makeblock_LE10a56219d0f1. Conexión BLE directa desde Python mediante Bleak. No necesita un puerto serie Bluetooth ni mantener mBlock conectado.

## Usar en este Mac

1. Enciende el Ranger con baterías. El cable USB se usó para cargar el programa; puedes retirarlo para usar Bluetooth.
2. Mantén mBlock y las aplicaciones del teléfono desconectadas del robot.
3. Abre Iniciar_Bluetooth.command con doble clic desde Finder.
4. Escribe un comando y pulsa Enter.

- `w`: avanzar durante 0.5 segundos.
- `s`: retroceder durante 0.5 segundos.
- `a` / `d`: girar a izquierda / derecha durante 0.5 segundos.
- `w 2`: avanzar durante 2 segundos y parar. También se aplica a s/a/d; máximo 10 segundos.
- `x`: parar.
- `1` / `2` / `3`: luces rojas / verdes / azules.
- `0`: apagar luces.
- `p`: sonido.
- `q`: salir.

La dirección de los motores conserva la configuración original para el montaje de orugas. No se probaron movimientos físicos. Coloca el robot sobre el suelo despejado para la primera prueba.

## Desde tu propio script

Python 3.11 o posterior y `pip install bleak`. En este Mac ya está instalado en el entorno de esta tarea.
Coloca tu script junto a ranger_bluetooth.py:

```python
import asyncio
from ranger_bluetooth import RangerBluetooth

async def main():
    async with RangerBluetooth() as robot:
        await robot.enviar("3")     # Luz azul; manda literalmente el byte ASCII 3.
        await robot.mover("w", 1)   # Avanza durante 1 segundo y envía x al terminar.
        await robot.enviar("x")     # Detiene los motores.

asyncio.run(main())
```

`await robot.enviar("w")` envía literalmente la letra w. El programa de la placa detiene los motores tras 600 ms sin recibir otra orden de movimiento. `mover()` repite la letra cada 150 ms aproximadamente durante el tiempo indicado y envía x al finalizar. No envíes comandos concurrentes desde varias tareas.

## Archivos

- ranger_bluetooth.py: controlador Python BLE.
- ranger_bluetooth.ino: copia del receptor cargado mediante mBlock.
- ranger-bluetooth.mblock: proyecto preparado con ese receptor.
- ranger-original.mblock y ranger-original.ino: respaldo anterior a los cambios.

El acceso Iniciar_Bluetooth.command usa ../work/venv; conserva la estructura de carpetas en este Mac. Para trasladarlo, instala bleak y ejecuta `python3 ranger_bluetooth.py`.

## Verificación realizada

El robot respondió por Bluetooth `RANGER_READY_V1`, `OK x` y `OK 3`. La prueba Bluetooth se hizo con el USB todavía conectado como alimentación; no se enviaron movimientos. El uso sin USB requiere baterías encendidas.

Si no encuentra el robot, revisa alimentación, cercanía y que ninguna otra app lo tenga conectado. Si macOS solicita acceso Bluetooth para Terminal/Python, permítelo para usar el controlador. Si indica que no responde el receptor, carga ranger_bluetooth.ino con mBlock por USB; restaurar el firmware de fábrica sustituye este receptor de letras.
