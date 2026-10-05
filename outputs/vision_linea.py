#!/usr/bin/env python3
"""Primera etapa: visualizar líneas negras desde la LifeCam externa."""
import argparse
import json
from pathlib import Path
import time
import cv2
import numpy as np
from vision_ranger import Camera
from vision_core import black_lines


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostico')
    parser.add_argument('--duracion', type=float, default=0)
    args = parser.parse_args()
    diagnostic = Path(args.diagnostico) if args.diagnostico else None
    if diagnostic:
        diagnostic.mkdir(parents=True, exist_ok=True)
    camera = Camera()
    window = 'Ranger | Detectar linea negra'
    last_saved = 0
    start = time.monotonic()
    try:
        cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        cv2.createTrackbar('Contraste', window, 30, 100, lambda _: None)
        while not args.duracion or time.monotonic() - start < args.duracion:
            sample = camera.read()
            now = time.monotonic()
            frame, stamp = sample if sample else (np.zeros((480, 640, 3), np.uint8), 0)
            fresh = now - stamp < .3
            contrast = max(10, cv2.getTrackbarPos('Contraste', window))
            lines = black_lines(frame, contrast) if fresh else []
            view = frame.copy()
            for line in lines:
                a, b = tuple(line[:2]), tuple(line[2:])
                cv2.line(view, a, b, (0, 255, 0), 3, cv2.LINE_AA)
                cv2.circle(view, a, 5, (0, 255, 255), -1)
                cv2.circle(view, b, 5, (0, 255, 255), -1)
            message = ('LINEA NEGRA DETECTADA' if lines else 'Buscando una linea negra...') if fresh else 'Esperando imagen de la webcam...'
            panel = np.full((125, frame.shape[1], 3), 24, np.uint8)
            rows = [message, 'Camara: ' + camera.name,
                    'Solo deteccion visual. Robot sin control en este modo.',
                    'Contraste: sube si marca juntas del piso; baja si no ve cinta.',
                    'Q: salir | No hace falta un recuadro completo.']
            for i, row in enumerate(rows):
                color = (80, 240, 80) if i == 0 and lines else (230, 230, 230)
                cv2.putText(panel, row, (10, 22+i*24), cv2.FONT_HERSHEY_SIMPLEX, .43, color, 1, cv2.LINE_AA)
            view = np.vstack([view, panel])
            cv2.imshow(window, view)
            if diagnostic and now-last_saved >= 1:
                cv2.imwrite(str(diagnostic/'camara.jpg'), frame)
                cv2.imwrite(str(diagnostic/'vista.jpg'), view)
                (diagnostic/'estado.json').write_text(json.dumps({
                    'time': time.time(), 'camera': camera.name, 'fresh': fresh,
                    'lines': [line.tolist() for line in lines], 'message': message
                }, indent=2), encoding='utf-8')
                last_saved = now
            if cv2.waitKey(20) & 0xff == ord('q') or cv2.getWindowProperty(window, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        camera.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit('Error: ' + str(exc))
