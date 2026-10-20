#!/usr/bin/env python3
"""Prepara firmware y actualiza por USB un Ranger identificado. Nunca carga por BLE."""
import argparse
from pathlib import Path
import shutil
import subprocess
import time

BASE=Path(__file__).resolve().parent
VERSION='RANGER_READY_V2_20261019'
MBLOCK=Path('/Applications/mBlock.app/Contents/Resources/ml/v1/external/arduino')

def identify(port, timeout=4):
    import serial
    with serial.Serial(port,115200,timeout=.15,write_timeout=1) as conn:
        time.sleep(2.5)
        conn.write(b'x?')
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            line=conn.readline().decode('ascii',errors='replace').strip()
            if line.startswith('RANGER_READY_'): return line
    return None

def candidates():
    from serial.tools import list_ports
    # Solo puertos USB; nunca Bluetooth virtual. La identificación de protocolo es obligatoria.
    return [p.device for p in list_ports.comports() if p.vid is not None]

def compile_firmware(root=MBLOCK):
    build=BASE.parent/'work/firmware-v2';build.mkdir(parents=True,exist_ok=True)
    root=Path(root);tool=root/'avr-toolchain/bin'
    if not (tool/'avr-g++').is_file() or not (root/'ranger/libranger.a').is_file():
        raise RuntimeError('Falta el compilador AVR de mBlock. Usa --toolchain con su carpeta arduino; compilación probada en Mac.')
    includes=['avr-library/cores/arduino','avr-library/variants/mega','arduino-libraries/makeblock/src',
              'arduino-libraries/makeblock/src/utility/avr','avr-library/libraries/Wire/src',
              'avr-library/libraries/SoftwareSerial/src','avr-library/libraries/SPI/src','avr-library/libraries/EEPROM/src']
    flags=['-x','c++','-c','-Os','-std=gnu++11','-fno-exceptions','-ffunction-sections','-fdata-sections',
           '-fno-threadsafe-statics','-mmcu=atmega2560','-DF_CPU=16000000L','-DARDUINO=10605',
           '-DARDUINO_AVR_MEGA2560','-DARDUINO_ARCH_AVR',*['-I'+str(root/p) for p in includes]]
    objects=[]
    # Compilar Tone explícitamente permite el pitido asíncrono aunque el archivo precompilado no lo incluya.
    for source,name in [(BASE/'ranger_bluetooth.ino','receptor'),(root/'avr-library/cores/arduino/Tone.cpp','tone')]:
        obj=build/(name+'.o');objects.append(str(obj))
        subprocess.run([str(tool/'avr-g++'),*flags,str(source),'-o',str(obj)],check=True,capture_output=True,text=True)
    subprocess.run([str(tool/'avr-gcc'),'-Os','-Wl,--gc-sections','-mmcu=atmega2560','-o',str(build/'receptor.elf'),
                    *objects,str(root/'ranger/libranger.a'),'-lm'],check=True,capture_output=True,text=True)
    target=build/'receptor.hex'
    subprocess.run([str(tool/'avr-objcopy'),'-O','ihex','-R','.eeprom',str(build/'receptor.elf'),str(target)],check=True)
    return target

def update(port, root=MBLOCK, initial=False, log=print):
    current=identify(port)
    if current==VERSION:
        log('Ranger actualizado: '+VERSION);return VERSION
    if current!='RANGER_READY_V1' and not initial:
        raise RuntimeError('No se identificó un receptor Ranger V1. No se cargó ningún programa. Para placa de fábrica usa --puerto y --carga-inicial de forma explícita.')
    log('Compilando y actualizando Ranger por USB...')
    image=compile_firmware(root)
    tool=Path(root)/'avr-toolchain'
    subprocess.run([str(tool/'bin/avrdude'),'-C',str(tool/'etc/avrdude.conf'),'-p','atmega2560','-c','wiring',
                    '-P',port,'-b','115200','-D','-U',f'flash:w:{image}:i'],check=True,capture_output=True,text=True)
    # avrdude verifica la memoria por defecto. Verificar también el protocolo tras reinicio.
    if identify(port)!=VERSION: raise RuntimeError('Se cargó el archivo, pero falta confirmar la versión. Mantén USB conectado.')
    log('Actualización verificada: '+VERSION);return VERSION

def update_if_present(log=print):
    ports=candidates()
    if not ports:
        log('Sin USB: se comprobará la versión por Bluetooth.');return None
    if len(ports)!=1:
        raise RuntimeError('Varios dispositivos USB serie. Actualiza con --puerto para elegir el Ranger.')
    return update(ports[0],log=log)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--esperar',action='store_true',help='Esperar a conectar USB y actualizar una vez')
    p.add_argument('--puerto');p.add_argument('--compilar',action='store_true')
    p.add_argument('--toolchain',type=Path,default=MBLOCK)
    p.add_argument('--carga-inicial',action='store_true')
    args=p.parse_args()
    if args.compilar: print(compile_firmware(args.toolchain));return
    if args.carga_inicial and not args.puerto: p.error('--carga-inicial requiere --puerto explícito')
    while True:
        ports=[args.puerto] if args.puerto else candidates()
        if len(ports)>1: raise RuntimeError('Varios puertos USB: elige con --puerto.')
        if ports:
            update(ports[0],args.toolchain,args.carga_inicial);return
        if not args.esperar: raise RuntimeError('Conecta el Ranger por USB o usa --esperar.')
        print('Esperando Ranger por USB... Ctrl+C cancela.',flush=True);time.sleep(2)

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('Espera cancelada.')
    except subprocess.CalledProcessError as e: raise SystemExit('Error del compilador/cargador: '+(e.stderr or str(e)))
    except Exception as e: raise SystemExit(str(e))
