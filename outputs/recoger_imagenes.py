#!/usr/bin/env python3
"""Recoge imágenes originales de la cámara externa para entrenar un detector de residuos.

Cada sesión se guarda en work/dataset/imagenes/<sesión>/. Conviene que cada sesión sea una
disposición distinta (otro día, otra luz, otra altura): al entrenar, una sesión completa se
reserva para comprobar el modelo con imágenes que no ha visto.
"""
import argparse
import json
from pathlib import Path
import subprocess
import time
import cv2
import numpy as np
from camaras_mac import camera_arg, size_arg
from vision_ranger import Camera

DATASET = Path(__file__).resolve().parents[1] / 'work/dataset/imagenes'
WINDOW = 'Recoger imagenes de residuos'
TIPS = [
    'Pon cada residuo en sitios distintos del recuadro, tambien junto a la cinta',
    'Gira los residuos y dales la vuelta',
    'Junta dos o tres residuos; que alguno tape un poco a otro',
    'Deja algun residuo fuera del recuadro',
    'Mete el robot en algunas fotos',
    'Haz algunas fotos sin ningun residuo',
]
SOUND = Path('/System/Library/Sounds/Tink.aiff')


class Recorder:
    """Numera y guarda fotos; en automático propone una cada `every` segundos."""
    def __init__(self, folder, auto=False, every=2., sharpness=60.):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        numbers = [int(p.stem) for p in self.folder.glob('*.jpg') if p.stem.isdigit()]
        self.next = max(numbers, default=-1) + 1
        self.saved = 0
        self.auto = auto
        self.every = every
        self.sharpness = sharpness
        self.last = -float('inf')

    def due(self, now):
        return self.auto and now - self.last >= self.every

    def problem(self, full, unchanged):
        # Camo envía imágenes negras idénticas cuando el teléfono no transmite.
        if full is None:
            return 'Sin imagen de la camara'
        if float(full.mean()) < 15:
            return 'Imagen negra: revisa Camo y el telefono'
        if unchanged > 2:
            return 'Imagen congelada: revisa Camo y el telefono'
        return None

    def blurry(self, full):
        """Varianza del laplaciano a 640 px. Medido: fotos movidas 26-34; nítidas 95-600."""
        if not self.sharpness:
            return False
        small = cv2.resize(full, (640, round(640 * full.shape[0] / full.shape[1])), interpolation=cv2.INTER_AREA)
        return cv2.Laplacian(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), cv2.CV_64F).var() < self.sharpness

    def save(self, full, now):
        path = self.folder / f'{self.next:04d}.jpg'
        if not cv2.imwrite(str(path), full, [cv2.IMWRITE_JPEG_QUALITY, 95]):
            raise RuntimeError('No se pudo guardar ' + str(path))
        self.next += 1
        self.saved += 1
        self.last = now
        return path


def beep():
    if SOUND.is_file():
        subprocess.Popen(['afplay', str(SOUND)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sesion', default=time.strftime('%Y%m%d-%H%M'),
                        help='Nombre de la sesion; si ya existe, se continua la numeracion')
    parser.add_argument('--auto', action='store_true', help='Empezar guardando automaticamente')
    parser.add_argument('--cada', type=float, default=2., help='Segundos entre fotos automaticas (1-30)')
    parser.add_argument('--camara', type=camera_arg, help='Nombre (lifecam, samsung, camo) o numero de una camara externa')
    parser.add_argument('--resolucion', type=size_arg, help='Captura ANCHOxALTO, p. ej. 1920x1080')
    parser.add_argument('--nitidez-min', type=float, default=60,
                        help='Por debajo, el modo automatico no guarda (foto movida); 0 lo desactiva')
    parser.add_argument('--duracion', type=float, default=0, help='Cerrar tras N segundos (prueba)')
    args = parser.parse_args()
    if not 1 <= args.cada <= 30:
        parser.error('--cada debe estar entre 1 y 30 segundos.')
    if not args.sesion.replace('-', '').replace('_', '').isalnum():
        parser.error('La sesion solo puede tener letras, numeros, - y _.')
    recorder = Recorder(DATASET / args.sesion, args.auto, args.cada, max(0., args.nitidez_min))
    camera = Camera(args.camara, args.resolucion)
    info = {'sesion': args.sesion, 'camara': camera.name, 'tamano': list(camera.size), 'inicio': time.time()}
    start = time.monotonic()
    flash = 0
    notice = ''
    print(f'Guardando en {recorder.folder}', flush=True)
    try:
        cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
        while not args.duracion or time.monotonic() - start < args.duracion:
            sample = camera.read_detail()
            now = time.monotonic()
            frame, full = (sample[0], sample[1]) if sample else (np.zeros(camera.work_shape, np.uint8), None)
            problem = recorder.problem(full, now - camera.changed)
            key = cv2.waitKey(15) & 0xff
            if key == ord('q') or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key == ord('a'):
                recorder.auto = not recorder.auto
                recorder.last = now  # la primera foto automática llega tras el intervalo
            manual = key == ord(' ')
            if (manual or recorder.due(now)) and problem:
                notice = 'NO GUARDADA: ' + problem
                recorder.last = now
            elif manual or recorder.due(now):
                blurry = recorder.blurry(full)
                if blurry and not manual:
                    # En automático no se guardan fotos movidas; con Espacio se guarda igualmente.
                    notice = 'NO GUARDADA: foto movida o borrosa; deja el telefono quieto'
                    recorder.last = now
                else:
                    path = recorder.save(full, now)
                    notice = 'Guardada ' + path.name + (' (parece borrosa)' if blurry else '')
                    flash = now
                    beep()
            view = frame.copy()
            if now - flash < .25:
                cv2.rectangle(view, (0, 0), (view.shape[1] - 1, view.shape[0] - 1), (255, 255, 255), 12)
            panel = np.full((150, view.shape[1], 3), 24, np.uint8)
            mode = (f'AUTOMATICO: foto en {max(0, recorder.every - (now - recorder.last)):.0f} s'
                    if recorder.auto else 'MANUAL: Espacio guarda una foto')
            rows = [f'Sesion {args.sesion} | Fotos guardadas: {recorder.saved} | {mode}',
                    'Consejo: ' + TIPS[(recorder.saved // 15) % len(TIPS)],
                    problem or notice,
                    'Espacio: foto | A: automatico si/no | Q: salir',
                    'Camara: ' + camera.summary()]
            for i, text in enumerate(rows):
                color = (80, 80, 255) if (i == 2 and (problem or notice.startswith('NO'))) else (230, 230, 230)
                cv2.putText(panel, text[:92], (10, 24 + i * 27), cv2.FONT_HERSHEY_SIMPLEX, .45, color, 1, cv2.LINE_AA)
            cv2.imshow(WINDOW, np.vstack([view, panel]))
    finally:
        camera.close()
        cv2.destroyAllWindows()
        info.update(fin=time.time(), guardadas=recorder.saved, total=len(list(recorder.folder.glob('*.jpg'))))
        log = recorder.folder / 'sesiones.jsonl'
        with log.open('a', encoding='utf-8') as handle:
            handle.write(json.dumps(info) + '\n')
        print(f'Fotos guardadas en esta ejecucion: {recorder.saved}; total de la sesion: {info["total"]}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit('Error: ' + str(exc))
