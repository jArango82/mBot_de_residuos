# Bluetooth, firmware y scripts propios

[Inicio](../README.md) · [Instalación por sistema](INSTALACION.md)

## Qué necesita la placa

El Ranger debe tener el receptor `outputs/ranger_bluetooth.ino`. El programa de fábrica no interpreta necesariamente las letras de este proyecto. El archivo `outputs/ranger-bluetooth.mblock` conserva el proyecto preparado; `ranger-original.mblock` y `ranger-original.ino` son respaldos anteriores.

Para cargarlo, conecta el Ranger por USB, abre el proyecto preparado en una versión de mBlock compatible con ese archivo, selecciona el dispositivo mBot Ranger y su puerto y utiliza la función de carga a la placa. La interfaz varía según la versión de mBlock; este repositorio no incluye un instalador ni una carga automática. El código depende de la biblioteca Makeblock que proporciona `MeAuriga.h`; un Arduino IDE sin esa biblioteca no podrá compilarlo. No uses un comando de carga genérico con una placa o puerto supuestos.

Una vez terminada la carga, desconecta mBlock del dispositivo antes de usar Python. El receptor responde a `?` con `RANGER_READY_V1`. Al arrancar enciende verde y da un pitido; la aplicación de visión apaga ese anillo al conectar. Restaurar el firmware de fábrica sustituye el receptor personalizado. La carga y verificación original se hicieron en Mac; no hay procedimiento de carga validado en Windows o Linux dentro de este proyecto.

Para usar BLE sin cable USB, enciende las baterías del robot y deja el módulo conectado. La prueba BLE original se hizo con USB presente como alimentación; queda por verificar el montaje completo funcionando solo con baterías.

## Conectar y probar sin movimiento

Usa el Python del entorno de tu sistema: `work/venv/bin/python` en Mac/Linux o `.\work\venv\Scripts\python.exe` en PowerShell. Los siguientes ejemplos usan la forma de Mac/Linux:

```sh
work/venv/bin/python outputs/ranger_bluetooth.py --listar
work/venv/bin/python outputs/ranger_bluetooth.py --comando x
work/venv/bin/python outputs/ranger_bluetooth.py --comando p
```

El nombre predeterminado es `Makeblock_LE10a56219eb91`, correspondiente al módulo del montaje original. Si aparece otro:

```sh
work/venv/bin/python outputs/ranger_bluetooth.py --nombre "NOMBRE_ENCONTRADO" --comando p
```

La búsqueda acepta nombre BLE o identificador anunciado. No asumas que el identificador tendrá el mismo formato en todos los sistemas. El controlador valida la respuesta del receptor antes de aceptar la conexión. Se conecta directamente mediante Bleak; no necesita un puerto serie Bluetooth.

## Control manual en consola

```sh
work/venv/bin/python outputs/ranger_bluetooth.py
```

Escribe una orden y pulsa Enter:

- `w`: adelante; `s`: atrás; `a`: izquierda; `d`: derecha. Por defecto 0.5 segundos.
- `w 2`: avanzar dos segundos; la duración también sirve para `a`, `s`, `d`. Debe ser mayor que cero y como máximo 10 segundos.
- `x`: detener motores.
- `0`: apagar LED; `1`: rojo; `2`: verde; `3`: azul.
- `p`: detener y emitir un pitido de unos 200 ms.
- `q`: salir de la consola y solicitar parada; esta letra no se envía al firmware.

También puedes usar `--comando w --segundos 0.5` para una orden individual. No ejecutes esa prueba hasta comprobar alimentación, sentido de motores y espacio disponible. Los motores conservan la configuración del montaje de orugas; no se ha validado físicamente su desplazamiento. **La consola no mira la webcam ni lee el sensor de línea.**

## Desde un script Python

Guarda tu script dentro de `outputs`, junto a `ranger_bluetooth.py`, y ejecútalo con el Python del entorno. Ejemplo de conexión y buzzer, sin movimiento:

```python
import asyncio
from ranger_bluetooth import RangerBluetooth

async def main():
    async with RangerBluetooth() as robot:
        await robot.enviar("0")
        await robot.enviar("p")
        await robot.enviar("x")

asyncio.run(main())
```

Para un movimiento supervisado, dentro del bloque puedes utilizar `await robot.mover("w", 0.5)`. `enviar("w")` envía una letra una vez; `mover()` repite la orden aproximadamente cada 150 ms durante la duración indicada y envía `x` al terminar. No envíes comandos concurrentes desde varias tareas o aplicaciones. Para otro módulo, construye `RangerBluetooth(nombre="NOMBRE_ENCONTRADO")`.

## Protocolo para desarrolladores

Transporte BLE del módulo utilizado:

- Escritura TX: `0000ffe3-0000-1000-8000-00805f9b34fb`, sin respuesta GATT.
- Notificaciones RX: `0000ffe2-0000-1000-8000-00805f9b34fb`.
- Letras ASCII; respuesta de aplicación `OK <letra>` terminada en salto de línea.
- `?` identifica el receptor. Orden desconocida: parada y `ERR_COMMAND`.
- La placa usa `Serial` a 115200 y potencia fija 100/255. No interpreta duración ni velocidad en el texto: esos tiempos los administra Python.
- Tras más de 600 ms sin nueva letra de movimiento, el firmware detiene y emite `AUTO_STOP`. No consulta sensores para decidir esa parada.

## Control USB conservado

`outputs/ranger.py` y `outputs/ranger_usb.ino` corresponden al controlador USB. Requiere instalar `pyserial`, que no está en `requirements_vision.txt`:

```sh
work/venv/bin/python -m pip install pyserial
work/venv/bin/python outputs/ranger.py --listar
work/venv/bin/python outputs/ranger.py --puerto /dev/cu.PUERTO_REAL --comando p
```

Sustituye el puerto de ejemplo por el enumerado. El script abre a 115200 y puede reiniciar la placa. Su autodetección de puerto está orientada a nombres de Mac y usa `exclusive=True`; no se presenta como un controlador USB validado para Windows/Linux. Para esos sistemas sigue la ruta BLE documentada. Nunca abras USB desde Python y mBlock simultáneamente.
