#!/usr/bin/env python3
"""Webcam cenital, límite negro, ArUco y objetos; control BLE con protección."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import threading
import time

BASE = Path(__file__).resolve().parent
os.environ.setdefault('YOLO_CONFIG_DIR', str(BASE.parent / 'work' / 'yolo-config'))
os.environ.setdefault('MPLCONFIGDIR', str(BASE.parent / 'work' / 'matplotlib'))
import cv2
import numpy as np
from vision_core import (assess, black_enclosures, calibrate_body,
                        marker_pose, same_boundary)
from ranger_bluetooth import RangerBluetooth, NOMBRE
from camaras_mac import select_external

WINDOW = 'Ranger | Vision y limite'


class Camera:
    def __init__(self, requested=None):
        import AVFoundation as av
        status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
        if status == 0:
            ready = threading.Event()
            av.AVCaptureDevice.requestAccessForMediaType_completionHandler_(
                av.AVMediaTypeVideo, lambda granted: ready.set())
            print('Acepta el permiso de camara de macOS para continuar.', flush=True)
            ready.wait(30)
            status = av.AVCaptureDevice.authorizationStatusForMediaType_(av.AVMediaTypeVideo)
        if status != 3:
            raise RuntimeError('Activa el permiso de Camara para la app que ejecuta Python y vuelve a abrir el programa.')
        index, self.name, self.device_id = select_external(requested)
        self.capture = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        # Una conexión/desconexión durante la apertura puede desplazar índices.
        try:
            if select_external(index)[2] != self.device_id:
                raise RuntimeError('Cambio la lista de camaras. Vuelve a abrir el programa.')
        except Exception:
            self.capture.release()
            raise
        self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if not self.capture.isOpened():
            raise RuntimeError('No se pudo abrir la webcam. Revisa el permiso de camara.')
        print(f'Camara: {self.name}; OpenCV={index}; ID={self.device_id}', flush=True)
        self.latest = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            while not self.stop.is_set():
                ok, frame = self.capture.read()
                if not ok:
                    time.sleep(.02)
                    continue
                with self.lock:
                    self.latest = (frame, time.monotonic())
        finally:
            self.capture.release()

    def read(self):
        with self.lock:
            return self.latest

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


class WasteDetector:
    """La inferencia es independiente: nunca retrasa la protección del borde."""
    def __init__(self, camera, model, classes):
        self.camera = camera
        self.model_path = model
        self.classes = classes
        self.latest = ([], 0)
        self.latest_details = ([], 0)
        self.status = 'Cargando detector de objetos...'
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        try:
            from ultralytics import YOLO, settings
            settings.update({'sync': False})
            if not Path(self.model_path).is_file():
                raise RuntimeError('Falta el modelo local: ' + self.model_path)
            model = YOLO(self.model_path)
            from vision_residuos import StableObjects, category
            stable = StableObjects()
            classes = self.classes if self.classes is not None else list(model.names.values())
            ids = [k for k, v in model.names.items() if v in classes]
            missing = set(classes) - set(model.names.values())
            if missing:
                raise RuntimeError('Modelo sin estas clases: ' + ', '.join(sorted(missing)))
            if not ids:
                raise RuntimeError('No hay categorias de objetos seleccionadas.')
            self.status = f'Detector activo: {len(ids)} categorias'
            last = 0
            while not self.stop.is_set():
                sample = self.camera.read()
                if sample is None or sample[1] == last:
                    self.stop.wait(.05)
                    continue
                frame, stamp = sample
                last = stamp
                results = model.predict(frame, imgsz=640, conf=.24, classes=ids,
                                        device='cpu', verbose=False)
                boxes = []
                for b in results[0].boxes:
                    boxes.append((b.xyxy[0].cpu().numpy().astype(int).tolist(),
                                  category(model.names[int(b.cls.item())]), float(b.conf.item())))
                details = stable.update(boxes,stamp)
                self.latest_details = (details,stamp)
                self.latest = ([(b,n,c) for b,n,c,_ in details], stamp)
                self.stop.wait(.12)
        except Exception as exc:
            self.status = 'Detector no disponible: ' + str(exc)


class CommandState:
    def __init__(self):
        self.lock = threading.Lock()
        self.snapshot = (0, False, False, 'x', 0)

    def set(self, safe=False, armed=False, command='x', until=0):
        with self.lock:
            self.snapshot = (time.monotonic(), safe, armed, command, until)

    def get(self):
        with self.lock:
            return self.snapshot


class BluetoothGuard:
    """Único dueño del enlace. Descarta movimiento vencido y no lo encola."""
    def __init__(self, state, name):
        self.state = state
        self.name = name
        self.stop = threading.Event()
        self.status = 'Bluetooth desconectado (C para conectar)'
        self.thread = None
        self.connected = False

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True)
        self.thread.start()

    async def run(self):
        self.status = 'Buscando Ranger por Bluetooth...'
        robot = RangerBluetooth(self.name)
        # Deadline menor que el watchdog; no esperar 3 segundos ante una avería.
        async def send(c):
            return await asyncio.wait_for(robot.enviar(c), .45)
        try:
            await robot.conectar()
            await send('x')
            await send('0')  # La luz del anillo altera el seguimiento visual.
            self.connected = True
            self.status = 'Bluetooth conectado | LED apagados | Aviso por buzzer'
            alarm, last_beep, moving = False, 0, False
            while not self.stop.is_set():
                stamp, safe, armed, command, until = self.state.get()
                now = time.monotonic()
                fresh = now - stamp <= .30
                effective_safe = safe and fresh
                # Alarmar ante límite o pérdida de visión, incluso sin movimiento.
                alarm = not effective_safe
                if alarm:
                    await send('x')
                    moving = False
                    if now - last_beep > 2:
                        await send('p')
                        last_beep = now
                elif armed and command in 'wasd' and now < until:
                    await send(command)
                    moving = True
                else:
                    if moving:
                        await send('x')
                        moving = False
                await asyncio.sleep(.06)
        except Exception as exc:
            self.status = 'Bluetooth detenido: ' + (str(exc) or type(exc).__name__)
        finally:
            self.connected = False
            try:
                await asyncio.wait_for(robot.cerrar(), 1.5)
            except Exception:
                if robot.client:
                    try:
                        await robot.client.disconnect()
                    except Exception:
                        pass

    def close(self):
        self.state.set()
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=3)


def camera_index(requested=None):
    return select_external(requested)[0]


def marker_image():
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    marker = cv2.aruco.generateImageMarker(dictionary, 7, 600)
    page = np.full((850, 800), 255, np.uint8)
    page[100:700, 100:700] = marker
    cv2.putText(page, 'RANGER - ID 7 - ARRIBA = FRENTE', (48, 55),
                cv2.FONT_HERSHEY_SIMPLEX, .85, 0, 2)
    cv2.putText(page, 'Conservar el margen blanco al recortar', (48, 780),
                cv2.FONT_HERSHEY_SIMPLEX, .8, 0, 2)
    cv2.imwrite(str(BASE / 'Etiqueta_Ranger.png'), page)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--camara', type=int)
    p.add_argument('--nombre', default=NOMBRE)
    p.add_argument('--modelo', default=str(BASE / 'models' / 'yolo11n.pt'))
    p.add_argument('--clases', default='bottle,cup')
    p.add_argument('--velocidad-max', type=float, default=100,
                   help='Cota de velocidad en pixeles/segundo; calibrar en la imagen')
    p.add_argument('--margen', type=float, default=20)
    p.add_argument('--etiqueta', action='store_true')
    p.add_argument('--duracion', type=float, default=0, help='Cerrar tras N segundos (diagnostico)')
    p.add_argument('--captura', help='Guardar ultima vista anotada al cerrar')
    p.add_argument('--diagnostico', help='Carpeta local de capturas y estado para diagnostico')
    args = p.parse_args()
    if args.etiqueta:
        marker_image()
        return
    if not np.isfinite(args.velocidad_max) or args.velocidad_max <= 0 or not np.isfinite(args.margen) or args.margen < 0:
        p.error('Velocidad debe ser positiva y margen no negativo.')
    camera = Camera(args.camara)
    camera_name = camera.name
    detector = WasteDetector(camera, args.modelo, [s.strip() for s in args.clases.split(',')])
    aruco = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    state = CommandState()
    guard = BluetoothGuard(state, args.nombre)
    boundary, body_ratio, previous, pose = None, None, None, None
    armed, command, until, stable = False, 'x', 0, 0
    last_stamp, prev_candidate = 0, None
    candidate = None
    recent_speeds = []
    notice = 'Pon la etiqueta ID 7 sobre el Ranger y muestra todo el recuadro.'
    last_view = None
    last_diagnostic = 0
    diagnostic = Path(args.diagnostico) if args.diagnostico else None
    if diagnostic:
        diagnostic.mkdir(parents=True,exist_ok=True)
    start = time.monotonic()
    cv2.namedWindow(WINDOW, cv2.WINDOW_AUTOSIZE)
    cv2.createTrackbar('Negro', WINDOW, 70, 160, lambda _: None)
    try:
        while not args.duracion or time.monotonic() - start < args.duracion:
            sample = camera.read()
            now = time.monotonic()
            frame, stamp = sample if sample is not None else (np.zeros((480, 640, 3), np.uint8), 0)
            age = now - stamp
            threshold = cv2.getTrackbarPos('Negro', WINDOW)
            candidates = black_enclosures(frame, threshold) if age < .3 else []
            candidate = candidates[0] if candidates else None
            if stamp != last_stamp:
                stable = stable + 1 if candidate is not None and prev_candidate is not None and same_boundary(prev_candidate, candidates, 4) is not None else 0
                prev_candidate = candidate
            current_boundary = same_boundary(boundary, candidates) if boundary is not None else None
            pose = marker_pose(frame, aruco) if age < .3 else None
            speed, prediction = 0, None
            if pose is not None and previous is not None and stamp > previous[1] and stamp - previous[1] < .3:
                velocity = (pose.center - previous[0]) / (stamp - previous[1])
                speed = float(np.linalg.norm(velocity))
                prediction = pose.center + velocity * 1.25
                recent_speeds.append((now, speed))
            recent_speeds = [(t, v) for t, v in recent_speeds if now - t < 1]
            speed = max([v for _, v in recent_speeds], default=0)
            if stamp != last_stamp:
                previous = (pose.center.copy(), stamp) if pose is not None else None
                last_stamp = stamp
            decision = assess(current_boundary, pose, body_ratio, age,
                              args.velocidad_max, args.margen, speed, prediction)
            if not decision.safe or not guard.connected:
                armed, command, until = False, 'x', 0
            state.set(decision.safe, armed, command, until)
            view = frame.copy()
            if boundary is not None:
                color = (0, 200, 0) if current_boundary is not None else (0, 0, 255)
                cv2.polylines(view, [boundary.astype(int)], True, color, 3)
            elif candidate is not None:
                cv2.polylines(view, [candidate.astype(int)], True, (0, 220, 255), 3)
                cv2.putText(view, 'B: confirmar este recuadro', tuple(candidate[0].astype(int)),
                            cv2.FONT_HERSHEY_SIMPLEX, .48, (0, 180, 230), 2)
            if pose is not None:
                cv2.polylines(view, [pose.corners.astype(int)], True, (255, 200, 0), 2)
                center = tuple(pose.center.astype(int))
                cv2.putText(view, 'RANGER', center, cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 200, 0), 2)
                if body_ratio:
                    cv2.circle(view, center, int(body_ratio * pose.side), (255, 200, 0), 2)
                if decision.required:
                    cv2.circle(view, center, int(decision.required), (0, 120, 255), 1)
            boxes, result_stamp = detector.latest
            count = 0
            if now - result_stamp < 1.0:
                for (x1, y1, x2, y2), name, confidence in boxes:
                    center = ((x1+x2)/2, (y1+y2)/2)
                    if current_boundary is not None and cv2.pointPolygonTest(current_boundary, center, False) < 0:
                        continue
                    if pose is not None and body_ratio and np.linalg.norm(np.asarray(center) - pose.center) < body_ratio * pose.side:
                        continue
                    count += 1
                    label = {'bottle': 'botella', 'cup': 'vaso'}.get(name, name)
                    cv2.rectangle(view, (x1,y1), (x2,y2), (220, 100, 255), 2)
                    cv2.putText(view, f'{label} {confidence:.0%} (posible residuo)',
                                (max(0,x1), max(16,y1-5)), cv2.FONT_HERSHEY_SIMPLEX, .44, (220,100,255), 1)
            panel = np.full((235, frame.shape[1], 3), 24, np.uint8)
            border_message = ('Recuadro detectado - pulsa B para confirmar'
                              if boundary is None and candidate is not None else decision.reason)
            rows = [border_message, guard.status,
                    f'Movimiento: {"HABILITADO" if armed else "BLOQUEADO"} | Objetos visibles: {count}',
                    'B: fijar borde | R: seleccionar cuerpo | C: Bluetooth',
                    'E: habilitar | W/A/S/D: paso corto | Espacio: parar | Q: salir',
                    'N: recalibrar | Ajusta Negro para detectar cinta oscura',
                    detector.status, notice, 'Camara: ' + camera_name]
            for i, text in enumerate(rows):
                color = (90, 230, 90) if i == 0 and decision.safe else ((80, 90, 255) if i == 0 else (220,220,220))
                cv2.putText(panel, text[:91], (10, 22 + i*25), cv2.FONT_HERSHEY_SIMPLEX, .40, color, 1, cv2.LINE_AA)
            last_view = np.vstack([view, panel])
            if diagnostic and now-last_diagnostic >= 2:
                cv2.imwrite(str(diagnostic/'camara.jpg'),frame)
                cv2.imwrite(str(diagnostic/'vista.jpg'),last_view)
                status = {'time':time.time(),'camera':camera_name,'candidates':len(candidates),
                          'stable_frames':stable,'boundary_confirmed':boundary is not None,
                          'boundary_visible':current_boundary is not None,'frame_age':age,
                          'message':border_message,'robot_visible':pose is not None}
                (diagnostic/'estado.json').write_text(json.dumps(status,indent=2),encoding='utf-8')
                last_diagnostic=now
            cv2.imshow(WINDOW, last_view)
            key = cv2.waitKey(15) & 0xff
            if key == ord('q') or cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE) < 1:
                break
            if key in (ord(' '), ord('x')):
                armed, command, until = False, 'x', 0
                state.set(decision.safe)
            elif key == ord('b'):
                armed = False
                state.set()
                if stable >= 8 and candidate is not None:
                    boundary = candidate.copy()
                    body_ratio = None
                    notice = 'Borde confirmado. R: selecciona TODO el cuerpo del Ranger.'
                else:
                    notice = 'Falta un recuadro negro cerrado y estable. Ajusta Negro.'
            elif key == ord('r'):
                armed = False
                state.set()
                if pose is not None:
                    rect = cv2.selectROI('Selecciona TODO el robot y pulsa Enter', frame, False, False)
                    cv2.destroyWindow('Selecciona TODO el robot y pulsa Enter')
                    try:
                        body_ratio = calibrate_body(pose, rect)
                        notice = 'Cuerpo calibrado. C: conectar; E: habilitar cuando sea seguro.'
                    except ValueError as exc:
                        notice = str(exc)
                else:
                    notice = 'No se ve la etiqueta ArUco ID 7. Colocala arriba del robot.'
            elif key == ord('n'):
                boundary, body_ratio, armed = None, None, False
                state.set()
                notice = 'Recalibrar: B para borde; R para cuerpo.'
            elif key == ord('c'):
                guard.start()
            elif key == ord('e') and decision.safe and guard.connected:
                armed, command, until = True, 'x', 0
                notice = 'Pasos cortos con W/A/S/D. Se bloquea al acercarse al limite.'
            elif key in [ord(x) for x in 'wasd'] and armed and decision.safe:
                command, until = chr(key), time.monotonic() + .15
            # Actualizar inmediatamente tras las acciones de teclado.
            state.set(decision.safe, armed, command, until)
    finally:
        state.set()
        guard.close()
        detector.stop.set()
        camera.close()
        cv2.destroyAllWindows()
        if args.captura and last_view is not None:
            cv2.imwrite(args.captura, last_view)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit('Error: ' + str(exc))
