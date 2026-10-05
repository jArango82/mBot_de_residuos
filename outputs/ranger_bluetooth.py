#!/usr/bin/env python3
"""Envía letras por Bluetooth BLE al mBot Ranger; requiere bleak."""
import argparse
import asyncio
import math
from bleak import BleakClient, BleakScanner

NOMBRE = 'Makeblock_LE10a56219eb91'
TX = '0000ffe3-0000-1000-8000-00805f9b34fb'
RX = '0000ffe2-0000-1000-8000-00805f9b34fb'


class RangerBluetooth:
    def __init__(self, nombre=NOMBRE):
        self.nombre = nombre
        self.client = None
        self.lineas = asyncio.Queue()
        self.buffer = bytearray()

    def _recibir(self, _, datos):
        self.buffer.extend(datos)
        while b'\n' in self.buffer:
            linea, _, resto = self.buffer.partition(b'\n')
            self.buffer = bytearray(resto)
            self.lineas.put_nowait(linea.decode('ascii', errors='replace').strip())
        if len(self.buffer) > 4096:
            self.buffer.clear()

    async def _respuesta(self, esperado, timeout=3):
        async with asyncio.timeout(timeout):
            while True:
                linea = await self.lineas.get()
                if linea == esperado:
                    return linea
                if linea.startswith('ERR'):
                    raise RuntimeError(linea)

    async def conectar(self):
        dispositivo = await BleakScanner.find_device_by_filter(
            lambda d, a: self.nombre in (d.name, a.local_name, d.address), timeout=12)
        if dispositivo is None:
            raise RuntimeError(f'No se encontró {self.nombre}. Enciende el robot y desconéctalo de otras apps.')
        self.client = BleakClient(dispositivo, timeout=15)
        try:
            await self.client.connect()
            await self.client.start_notify(RX, self._recibir)
            await self.client.write_gatt_char(TX, b'?', response=False)
            await self._respuesta('RANGER_READY_V1')
            await self.enviar('x')
        except BaseException:
            await self.client.disconnect()
            raise

    async def enviar(self, letra):
        """Envía una letra ASCII y espera la confirmación del Ranger."""
        letra = letra.lower()
        if letra not in ('w', 's', 'a', 'd', 'x', '1', '2', '3', '0', 'p'):
            raise ValueError('Usa w, s, a, d, x, 1, 2, 3, 0 o p.')
        await self.client.write_gatt_char(TX, letra.encode('ascii'), response=False)
        return await self._respuesta('OK ' + letra)

    async def mover(self, letra, segundos=0.5):
        if letra not in ('w', 's', 'a', 'd'):
            raise ValueError('Movimiento: w, s, a o d.')
        if not math.isfinite(segundos) or not 0 < segundos <= 10:
            raise ValueError('La duración debe ser mayor que 0 y como máximo 10 segundos.')
        fin = asyncio.get_running_loop().time() + segundos
        try:
            while asyncio.get_running_loop().time() < fin:
                await self.enviar(letra)
                await asyncio.sleep(min(0.15, max(0, fin - asyncio.get_running_loop().time())))
        finally:
            if self.client.is_connected:
                await self.enviar('x')

    async def cerrar(self):
        if self.client and self.client.is_connected:
            try:
                await self.enviar('x')
            finally:
                await self.client.disconnect()

    async def __aenter__(self):
        await self.conectar()
        return self

    async def __aexit__(self, *_):
        await self.cerrar()


async def main():
    parser = argparse.ArgumentParser(description='Controla tu Ranger por Bluetooth BLE')
    parser.add_argument('--nombre', default=NOMBRE, help='Nombre BLE o identificador del robot')
    parser.add_argument('--listar', action='store_true', help='Buscar dispositivos BLE')
    parser.add_argument('--comando', choices=list('wsadx1230p'))
    parser.add_argument('--segundos', type=float, default=0.5)
    args = parser.parse_args()
    if args.listar:
        for d, a in (await BleakScanner.discover(timeout=8, return_adv=True)).values():
            if a.local_name or d.name:
                print(a.local_name or d.name, d.address)
        return
    print('Buscando', args.nombre, 'por Bluetooth…', flush=True)
    async with RangerBluetooth(args.nombre) as robot:
        print('Conectado por Bluetooth. Receptor de comandos confirmado.', flush=True)
        if args.comando:
            if args.comando in 'wsad':
                await robot.mover(args.comando, args.segundos)
                print('Movimiento terminado; robot detenido.')
            else:
                print(await robot.enviar(args.comando))
            return
        print('Escribe una letra y Enter: w adelante, s atrás, a izquierda, d derecha,')
        print('x parar, 1 rojo, 2 verde, 3 azul, 0 apagar luces, p sonido, q salir.')
        print('w mueve durante 0.5 s; w 2 mueve durante 2 s (máximo 10 s).')
        while True:
            # El bucle Bluetooth sigue activo mientras esperas para escribir.
            partes = (await asyncio.to_thread(input, 'Ranger > ')).lower().split()
            if not partes:
                continue
            if partes == ['q']:
                break
            try:
                if partes[0] in ('w', 's', 'a', 'd') and len(partes) <= 2:
                    await robot.mover(partes[0], float(partes[1]) if len(partes) == 2 else 0.5)
                    print('OK; detenido.')
                elif len(partes) == 1:
                    print(await robot.enviar(partes[0]))
                else:
                    print('Usa una letra y, para movimiento, una duración opcional.')
            except ValueError as exc:
                print(exc)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print('\nControl terminado.')
    except TimeoutError:
        raise SystemExit('Sin respuesta del robot. Revisa la alimentación y el programa cargado en mBlock.')
    except Exception as exc:
        raise SystemExit(f'Error Bluetooth: {exc}')
