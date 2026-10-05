#!/usr/bin/env python3
"""Control USB del Ranger con ranger_usb.ino. Usa pyserial."""
import argparse
import math
import time
import serial
from serial.tools import list_ports


class Ranger:
    def __init__(self, port=None):
        if port is None:
            ports = [p.device for p in list_ports.comports()
                     if 'usbserial' in p.device or 'usbmodem' in p.device]
            if len(ports) != 1:
                raise RuntimeError('Indica --puerto. Disponibles: ' + ', '.join(p.device for p in list_ports.comports()))
            port = ports[0]
        self.serial = serial.Serial(port, 115200, timeout=0.1, write_timeout=1, exclusive=True)
        try:
            time.sleep(2.5)  # La placa puede reiniciarse al abrir el puerto.
            self.serial.reset_input_buffer()
            self.serial.write(b'?')
            self._esperar('RANGER_READY_V1', 3)
            self.enviar('x')
        except BaseException:
            self.serial.close()
            raise

    def _esperar(self, esperado, timeout=1):
        fin = time.monotonic() + timeout
        while time.monotonic() < fin:
            linea = self.serial.readline().decode('ascii', errors='replace').strip()
            if linea == esperado:
                return linea
            if linea.startswith('ERR'):
                raise RuntimeError(linea)
        raise RuntimeError(f'Sin respuesta {esperado!r}. Revisa el programa cargado y desconecta mBlock.')

    def enviar(self, comando):
        comando = comando.lower()
        if comando not in ('w', 'a', 's', 'd', 'x', '0', '1', '2', '3', 'p'):
            raise ValueError('Comando no válido')
        self.serial.write(comando.encode('ascii'))
        return self._esperar('OK ' + comando)

    def mover(self, comando, segundos=0.5):
        if comando not in ('w', 'a', 's', 'd'):
            raise ValueError('Movimiento: w, a, s o d')
        if not math.isfinite(segundos) or not 0 < segundos <= 10:
            raise ValueError('Duración entre 0 y 10 segundos')
        fin = time.monotonic() + segundos
        try:
            while time.monotonic() < fin:
                self.enviar(comando)
                time.sleep(min(0.15, max(0, fin - time.monotonic())))
        finally:
            self.enviar('x')

    def close(self):
        if self.serial.is_open:
            try:
                self.enviar('x')
            finally:
                self.serial.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def main():
    parser = argparse.ArgumentParser(description='Control USB de mBot Ranger')
    parser.add_argument('--puerto', help='Ejemplo: /dev/cu.usbserial-1120')
    parser.add_argument('--listar', action='store_true')
    parser.add_argument('--comando', choices=list('wasdx0123p'))
    parser.add_argument('--segundos', type=float, default=0.5)
    args = parser.parse_args()
    if args.listar:
        for p in list_ports.comports():
            print(p.device, p.description)
        return
    with Ranger(args.puerto) as robot:
        print('Ranger conectado y firmware confirmado.')
        if args.comando:
            if args.comando in 'wasd':
                robot.mover(args.comando, args.segundos)
            else:
                print(robot.enviar(args.comando))
            return
        print('Escribe un comando y Enter: w adelante, s atrás, a izquierda, d derecha,')
        print('x parar, 1 rojo, 2 verde, 3 azul, 0 apagar luces, p sonido, q salir.')
        print('Cada movimiento dura 0.5 s. Puedes escribir: w 2 (máximo 10 s).')
        while True:
            partes = input('Ranger > ').lower().split()
            if not partes:
                continue
            if partes == ['q']:
                break
            try:
                if partes[0] in ('w', 'a', 's', 'd') and len(partes) <= 2:
                    robot.mover(partes[0], float(partes[1]) if len(partes) == 2 else 0.5)
                elif len(partes) == 1:
                    print(robot.enviar(partes[0]))
                else:
                    print('Usa un comando, opcionalmente con duración para movimiento.')
            except ValueError as exc:
                print(exc)


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nControl terminado.')
    except (serial.SerialException, RuntimeError, OSError) as exc:
        raise SystemExit(f'Error: {exc}')
