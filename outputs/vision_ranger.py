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
from camaras_mac import WATERMARKS, camera_arg, native_size, opencv_devices, profile, select_external

WINDOW = 'Ranger | Vision y limite'
# Lado mayor de la imagen de análisis. Borde, robot, conteo y dashboard se ajustaron a 640 px:
# una cámara de más resolución se reduce aquí y su detalle se usa solo para zoom y detectores.
WORK_SIZE = 640


def work_size(width, height, longest=WORK_SIZE):
    scale = max(width, height) / longest
    return (width, height) if scale <= 1 else (round(width / scale), round(height / scale))


def capture_size(kind, native, requested=None, longest=1280):
    """LifeCam a 640x480 como siempre; otras con su proporción real, hasta 1280 px."""
    if requested:
        return requested
    if kind == 'LifeCam':
        return 640, 480
    if native is None:
        return 1280, 720
    scale = max(native) / longest
    return native if scale <= 1 else (round(native[0] / scale), round(native[1] / scale))


def black_bars(frame):
    """Bandas negras uniformes: la proporción pedida no coincide y podrían parecer cinta."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if gray[h // 4:3 * h // 4, w // 4:3 * w // 4].max() < 12:
        return False  # Imagen todavía negra al arrancar: no indica bandas.
    rows, cols = max(2, h // 50), max(2, w // 50)
    return bool((gray[:rows].max() < 12 and gray[-rows:].max() < 12) or
                (gray[:, :cols].max() < 12 and gray[:, -cols:].max() < 12))


class Camera:
    def __init__(self, requested=None, resolution=None):
        import AVFoundation as av
        # Elegir antes del permiso: si falta la cámara externa, no se pide acceso a ninguna.
        devices = opencv_devices()
        index, self.name, self.device_id = select_external(requested, devices)
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
        kind = profile(devices[index])
        wanted = capture_size(kind, native_size(devices[index]), resolution)
        # Zona de la imagen que se ignora al detectar (marca de agua de la cámara virtual).
        self.ignore_zone = WATERMARKS.get(kind)
        self.capture = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
        try:
            # Una conexión/desconexión durante la apertura puede desplazar índices.
            if select_external(index)[2] != self.device_id:
                raise RuntimeError('Cambio la lista de camaras. Vuelve a abrir el programa.')
            self.capture.set(cv2.CAP_PROP_FRAME_WIDTH, wanted[0])
            self.capture.set(cv2.CAP_PROP_FRAME_HEIGHT, wanted[1])
            if not self.capture.isOpened():
                raise RuntimeError('No se pudo abrir la webcam. Revisa el permiso de camara.')
            first = self.first_frame()
        except Exception:
            self.capture.release()
            raise
        self.size = (first.shape[1], first.shape[0])
        self.work_size = work_size(*self.size)
        self.work_shape = (self.work_size[1], self.work_size[0], 3)
        self.scale = self.size[0] / self.work_size[0]
        print(f'Camara: {self.name}; OpenCV={index}; ID={self.device_id}; '
              f'imagen {self.size[0]}x{self.size[1]}; analisis {self.work_size[0]}x{self.work_size[1]}', flush=True)
        if self.size != tuple(wanted):
            print(f'Aviso: se pidio {wanted[0]}x{wanted[1]} y la camara entrega otro tamano.', flush=True)
        if self.size[1] > self.size[0]:
            print('Aviso: imagen vertical. Gira el telefono a horizontal para ver todo el recuadro.', flush=True)
        self.latest = None
        self.full = None
        self.previous = first
        self.changed = self.started = time.monotonic()
        self.bars_checked = False
        self.fps = 0.
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def first_frame(self, timeout=5):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            ok, frame = self.capture.read()
            if ok and frame is not None and frame.size:
                return frame
            time.sleep(.05)
        raise RuntimeError('La camara no entrega imagen. Revisa el telefono o su aplicacion de camara web.')

    def run(self):
        try:
            while not self.stop.is_set():
                ok, full = self.capture.read()
                if not ok or full is None:
                    time.sleep(.02)
                    continue
                now = time.monotonic()
                # Una cámara virtual (Camo) puede repetir la última imagen si se corta el teléfono.
                if (full is self.previous or full.shape != self.previous.shape or
                        not np.array_equal(full, self.previous)):
                    self.changed = now
                self.previous = full
                # Las cámaras virtuales envían imágenes de arranque: revisar pasado un segundo.
                if not self.bars_checked and now - self.started > 1:
                    self.bars_checked = True
                    if black_bars(full):
                        print('Aviso: la imagen tiene bandas negras; pueden confundirse con cinta. '
                              'Usa --resolucion con la proporcion de la camara.', flush=True)
                frame = (full if full.shape[1::-1] == self.work_size else
                         cv2.resize(full, self.work_size, interpolation=cv2.INTER_AREA))
                with self.lock:
                    if self.latest is not None:
                        self.fps = .9 * self.fps + .1 / max(now - self.latest[1], 1e-3)
                    self.latest = (frame, now)
                    self.full = full
        finally:
            self.capture.release()

    def read(self):
        with self.lock:
            return self.latest

    def read_detail(self):
        """Imagen de análisis y la original de la misma captura, para zoom y detectores."""
        with self.lock:
            return None if self.latest is None else (self.latest[0], self.full, self.latest[1])

    def summary(self):
        text = f'{self.name} | {self.size[0]}x{self.size[1]}'
        if self.size != self.work_size:
            text += f'>{self.work_size[0]}x{self.work_size[1]}'
        return text + f' | {self.fps:.0f} fps'

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)


class WasteDetector:
    """La inferencia es independiente: nunca retrasa la protección del borde."""
    def __init__(self, camera, model, classes, focus=None, custom=None):
        self.camera = camera
        self.focus = focus
        self.model_path = model
        self.classes = classes
        # Modelo entrenado con los residuos del usuario (opcional). Va en este mismo hilo: es el único
        # que usa la gráfica del Mac.
        self.custom_path = custom
        self.latest = ([], 0)
        self.latest_details = ([], 0)
        self.custom_details = ([], 0)
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
            from vision_residuos import KEEP_CONF, MODEL_LOCK, StableObjects, category, merge_observations, small_enough
            from vision_zoom import detail_sample, restore_crop, to_work
            with MODEL_LOCK:
                model = YOLO(self.model_path)
                classes = self.classes if self.classes is not None else list(model.names.values())
                ids = [k for k, v in model.names.items() if v in classes]
                missing = set(classes) - set(model.names.values())
                if missing:
                    raise RuntimeError('Modelo sin estas clases: ' + ', '.join(sorted(missing)))
                if not ids:
                    raise RuntimeError('No hay categorias de objetos seleccionadas.')
                # La gráfica del Mac (MPS) da los mismos resultados unas seis veces más rápido y permite
                # analizar la imagen del teléfono a 1280 px. Solo este hilo la usa: dos hilos a la vez
                # en MPS cierran el programa con un error de Metal.
                device = 'cpu'
                try:
                    import torch
                    if torch.backends.mps.is_available():
                        model.predict(np.zeros((480, 640, 3), np.uint8), imgsz=640, conf=KEEP_CONF,
                                      classes=ids, device='mps', verbose=False)
                        device = 'mps'
                except Exception:
                    model = YOLO(self.model_path)
                if device == 'cpu':
                    # La primera inferencia reorganiza capas: también debe ocurrir sin otra carga en curso.
                    model.predict(np.zeros((480, 640, 3), np.uint8), imgsz=640, conf=KEEP_CONF, classes=ids,
                                  device='cpu', verbose=False)
                own = None
                if self.custom_path and Path(self.custom_path).is_file():
                    own = YOLO(self.custom_path)
                    own.predict(np.zeros((480, 640, 3), np.uint8), imgsz=640, conf=KEEP_CONF, device=device, verbose=False)
            def detect(image, size):
                result = model.predict(image, imgsz=size, conf=KEEP_CONF, classes=ids, device=device, verbose=False)[0]
                return [(b.xyxy[0].cpu().numpy(), category(model.names[int(b.cls.item())]), float(b.conf.item()))
                        for b in result.boxes]
            stable = StableObjects()
            # Más exigente que los genéricos: sus objetos reales puntuaban 0,70-0,99 y lo que confundía en
            # imágenes de otra cámara, 0,26-0,53. Nuevo desde 0,6; ya seguido, desde 0,3.
            own_stable = StableObjects(new_conf=.6)
            self.status = (f'Detector activo: {len(ids)} categorias | ' + ('GPU' if device == 'mps' else 'CPU') +
                           (' | modelo propio' if own is not None else ''))
            last = 0
            while not self.stop.is_set():
                sample = detail_sample(self.camera)
                if sample is None or sample[2] == last:
                    self.stop.wait(.05)
                    continue
                frame, full, stamp = sample
                last = stamp
                scale = full.shape[1] / frame.shape[1]
                # Con GPU se analiza la imagen original del teléfono (hasta 1280 px); sin ella, la de 640.
                if device == 'mps':
                    boxes = to_work(detect(full, min(1280, max(full.shape[:2]))), scale)
                else:
                    boxes = detect(frame, 640)
                # El recorte del zoom sale de la imagen original: con el teléfono aporta detalle real.
                region = self.focus.region(full.shape) if self.focus is not None else None
                if region is not None:
                    x1,y1,x2,y2 = region
                    zoomed = restore_crop(detect(full[y1:y2,x1:x2], 640), region, full.shape)
                    boxes = merge_observations(boxes, to_work(zoomed, scale))
                if own is not None:
                    # Se analiza la imagen original a 960 px, el mismo tamaño con el que se entrenó.
                    result = own.predict(full, imgsz=960, conf=.3, device=device, verbose=False)[0]
                    found = small_enough([(b.xyxy[0].cpu().numpy(), own.names[int(b.cls.item())], float(b.conf.item()))
                                          for b in result.boxes], full.shape)
                    self.custom_details = (own_stable.update(to_work(found, scale), stamp), stamp)
                details = stable.update(boxes,stamp)
                self.latest_details = (details,stamp)
                self.latest = ([(b,n,c) for b,n,c,_ in details], stamp)
                self.stop.wait(.12)
        except Exception as exc:
            self.status = 'Detector no disponible: ' + str(exc)


class CommandState:
    def __init__(self):
        self.lock = threading.Lock()
        self.snapshot = (0, False, False, 'x', 0, False)

    def set(self, safe=False, armed=False, command='x', until=0, outside=False):
        with self.lock:
            self.snapshot = (time.monotonic(), safe, armed, command, until, outside)

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
                stamp, safe, armed, command, until, outside = self.state.get()
                now = time.monotonic()
                fresh = now - stamp <= .30
                effective_safe = safe and fresh
                # La línea no bloquea; una pérdida de vigilancia sí cancela pasos, en silencio.
                if effective_safe and armed and command in 'wasd' and now < until:
                    await send(command)
                    moving = True
                elif moving or not effective_safe:
                    await send('x')
                    moving = False
                if outside and effective_safe and now - last_beep > 2:
                    await send('p')  # V2: sonido no bloqueante, no toca motores.
                    last_beep = now
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
    p.add_argument('--camara', type=camera_arg, help='Nombre (lifecam, samsung, camo) o indice de una camara externa')
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
