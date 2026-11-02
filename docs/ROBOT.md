# Robot, Bluetooth y scripts propios

Actualizado: 2 de noviembre de 2026

Documento principal: [Documentación técnica del sistema](DOCUMENTACION_TECNICA.md).

[Inicio](../README.md) · [Operación y firmware](OPERACION_V2.md) · [Instalación](INSTALACION.md)

Este documento trata del robot por sí solo: su placa, cómo se conecta por Bluetooth, cómo moverlo desde una consola y cómo escribir un script propio. Para usarlo con la cámara, ver el [Manual de uso](USO.md).

## El robot

| Dato | Valor |
|---|---|
| Robot | mBot Ranger de Makeblock, montado con orugas |
| Placa | Auriga (microcontrolador ATmega2560) |
| Bluetooth | Módulo BLE llamado `Makeblock_LE10a56219eb91` |
| USB | Chip CH340; en el Mac de Juan aparece como `/dev/cu.usbserial-1120` |
| Firmware | `outputs/ranger_bluetooth.ino`, versión `RANGER_READY_V2_20261019`, cargado el 27/10 |

El firmware es nuestro receptor de letras (ver [Operación](OPERACION_V2.md#firmware-v2-qué-es-y-cómo-se-carga)): el programa de fábrica no entiende las órdenes de este proyecto. Si alguien restaura el programa de fábrica, hay que volver a cargarlo con `outputs/Actualizar_Ranger.command`.

Otros archivos de la placa:

- `outputs/ranger-bluetooth.mblock`: el mismo receptor como proyecto de mBlock, por si se quiere cargar desde mBlock (dispositivo mBot Ranger, su puerto y «subir»). La interfaz cambia según la versión de mBlock. El código necesita la biblioteca Makeblock (`MeAuriga.h`): un Arduino IDE sin ella no lo compila.
- `outputs/ranger-original.ino`, `outputs/ranger-original.mblock`: copia del programa anterior.

Después de cargar con mBlock, desconecta mBlock del robot antes de usar Python: dos programas no pueden usar el robot a la vez.

## Probar la conexión sin moverlo

Usa el Python del proyecto: `work/venv/bin/python` en Mac y Linux, `.\work\venv\Scripts\python.exe` en Windows (PowerShell). Los ejemplos usan la forma de Mac:

```sh
work/venv/bin/python outputs/ranger_bluetooth.py --listar
work/venv/bin/python outputs/ranger_bluetooth.py --comando x
work/venv/bin/python outputs/ranger_bluetooth.py --comando p
```

1. `--listar` busca robots cercanos. Debe aparecer `Makeblock_LE10a56219eb91`.
2. `--comando x` envía «parar».
3. `--comando p` hace pitar al robot. Si pita, la conexión y el firmware funcionan.

Si tu robot tiene otro nombre, añade `--nombre "NOMBRE_ENCONTRADO"`.

Al conectar, el programa comprueba que el firmware responde `RANGER_READY_V2_20261019`. Si encuentra una versión antigua, se niega a moverlo y pide conectar el cable USB para actualizarlo. Si hay un cable USB conectado, intenta actualizarlo antes. Necesita las bibliotecas Bleak y pyserial.

## Mover el robot desde la consola (sin cámara)

```sh
work/venv/bin/python outputs/ranger_bluetooth.py
```

Escribe una orden y pulsa Enter:

| Orden | Qué hace |
|---|---|
| `w`, `s`, `a`, `d` | Adelante, atrás, izquierda, derecha durante 0,5 s. |
| `w 2` | Adelante 2 s. Vale para las cuatro direcciones; entre 0 y 10 s. |
| `x` | Parar. |
| `0`, `1`, `2`, `3` | LED apagados, rojos, verdes, azules. |
| `p` | Pitido de ~200 ms, sin parar los motores. |
| `q` | Salir (antes pide parar). Esta letra no se envía al robot. |

También sirve una orden suelta: `--comando w --segundos 0.5`.

Antes de mover, comprueba que el robot está en el suelo, con batería, con espacio libre y sin cables que tiren de él. **La consola no mira la cámara ni la cinta**: no hay ninguna protección visual, solo el temporizador de 600 ms de la placa.

El movimiento del robot se ha probado con el programa de la cámara (27/10 al 2/11). La consola es una herramienta de prueba.

## Desde un script de Python

Guarda tu script en `outputs/`, junto a `ranger_bluetooth.py`, y ejecútalo con el Python del proyecto. Ejemplo que conecta, apaga los LED, pita y para, sin moverse:

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

- `await robot.mover("w", 0.5)` avanza medio segundo: repite la letra cada ~150 ms (para que la placa no se pare a los 600 ms) y envía `x` al terminar.
- `await robot.enviar("w")` envía la letra una sola vez (la placa se parará sola a los 600 ms).
- Para otro robot: `RangerBluetooth(nombre="NOMBRE_ENCONTRADO")`.
- No envíes órdenes desde varias tareas o programas a la vez.

## Protocolo, para quien programe

- Escritura (del Mac al robot): característica `0000ffe3-0000-1000-8000-00805f9b34fb`, sin respuesta.
- Avisos (del robot al Mac): característica `0000ffe2-0000-1000-8000-00805f9b34fb`.
- Cada orden es una letra. La placa responde `OK <letra>` y un salto de línea. Ante una letra desconocida, detiene los motores y responde `ERR_COMMAND`.
- `?` devuelve la versión.
- La placa usa el puerto serie a 115200 baudios y potencia fija 100 de 255. No entiende duraciones ni velocidades: los tiempos los decide Python.
- Tras 600 ms sin una letra de movimiento, para y envía `AUTO_STOP`.

El programa de la cámara (`BluetoothGuard` en `outputs/vision_ranger.py`) envía la orden vigente cada 60 ms y espera la confirmación como mucho 0,45 s. Tolera dos confirmaciones lentas seguidas; a la tercera cierra la conexión (antes, una sola la cortaba al empujar).

## Control por cable USB (antiguo)

`outputs/ranger.py` y `outputs/ranger_usb.ino` son el primer control por cable. Se conservan, pero no se usan con el firmware actual:

```sh
work/venv/bin/python outputs/ranger.py --listar
work/venv/bin/python outputs/ranger.py --puerto /dev/cu.PUERTO_REAL --comando p
```

Sustituye el puerto por el que aparezca en la lista. Abrir el puerto puede reiniciar la placa. Nunca abras el USB desde Python y desde mBlock a la vez.

## Windows y Linux

En Windows y Linux solo funciona esta parte (Bluetooth y consola), y **no se ha probado** con este robot. Los pasos de instalación están en [Instalación](INSTALACION.md#windows-solo-bluetooth). La carga del firmware y todo lo que usa la cámara son solo para Mac.
