#!/usr/bin/env python3
"""Prueba supervisada de cinta o recuadro y Ranger seleccionado, sin etiqueta."""
import argparse
import json
import math
from pathlib import Path
import time
import cv2
import numpy as np
from vision_core import black_lines, same_boundary, Decision
from vision_ranger import Camera, CommandState, BluetoothGuard, WasteDetector
from ranger_bluetooth import NOMBRE
from vision_boundary import AutoBoundary, tape_image
from vision_cinta import tape_squares, square_support
from vision_papel import PaperDetector
from vision_residuos import merge_observations, outside_zone, overlap
from vision_zoom import InspectionZoom, detail_sample
from camaras_mac import camera_arg, describe, size_arg
from vision_superres import SuperResolution
from conteo_residuos import EventStore, SeparationCounter
from aviso_n8n import N8nSender, DEFAULT_URL as N8N_URL
from navegacion import GoToWaste, covered
import vision_hojas
from vision_orugas import track_axis, plane_axis
from dashboard import LiveVideo, serve


def line_normal(line):
    a, b = np.asarray(line, float).reshape(2, 2)
    delta = b-a
    n = np.array([-delta[1], delta[0]]) / np.linalg.norm(delta)
    return a, n


def matching_line(reference, candidates):
    a, n = line_normal(reference)
    axis = np.array([n[1], -n[0]])
    length = np.linalg.norm(np.asarray(reference[2:])-reference[:2])
    for candidate in candidates:
        pts = np.asarray(candidate, float).reshape(2, 2)
        projection = (pts-a) @ axis
        overlap = min(length, projection.max())-max(0, projection.min())
        if np.max(np.abs((pts-a) @ n)) <= 10 and overlap >= length*.60:
            return candidate
    return None


def assess_line(reference, visible, box, side, age, speed=100, margin=20):
    if age > .30:
        return Decision(False, 'Imagen atrasada: detener')
    if reference is None or not visible:
        return Decision(False, 'Linea perdida o sin confirmar: detener')
    if box is None or side is None:
        return Decision(False, 'Selecciona TODO el Ranger con R')
    x, y, w, h = box
    a, n = line_normal(reference)
    corners = np.array([[x,y],[x+w,y],[x+w,y+h],[x,y+h]])
    clearance = float(np.min((corners-a) @ n * side))
    # Cruzar la cinta no bloquea motores. El aviso utiliza el cuerpo observado, sin reserva de frenado.
    return Decision(True, 'FUERA: aviso sonoro; manejo permitido' if clearance < -5 else 'Manejo permitido; aviso solo al salir', clearance, 0)


def frozen_while_moving(moving_since, changed, now, limit=.6):
    """En marcha, una imagen real cambia; si no cambia en 0,6 s la cámara está congelada."""
    return moving_since is not None and now-moving_since > limit and now-changed > limit


def appearance(frame, box):
    x, y, w, h = map(int, box)
    if x < 0 or y < 0 or x+w > frame.shape[1] or y+h > frame.shape[0] or min(w,h) < 15:
        return None
    hsv = cv2.cvtColor(frame[y:y+h, x:x+w], cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0,1], None, [24,16], [0,180,0,256])
    return cv2.normalize(hist, hist).flatten()


def assess_rectangle(boundary, visible, box, age, speed=100, margin=20):
    if boundary is None or not visible or age > .30:
        return Decision(False, 'Recuadro perdido o imagen atrasada: detener')
    if box is None:
        return Decision(False, 'Selecciona TODO el Ranger con R')
    center = boundary.mean(axis=0)
    decisions = []
    for a,b in zip(boundary,np.roll(boundary,-1,axis=0)):
        line = np.r_[a,b]
        origin,normal = line_normal(line)
        side = 1 if (center-origin) @ normal >= 0 else -1
        decisions.append(assess_line(line,True,box,side,age,speed,margin))
    nearest = min(decisions,key=lambda d:d.clearance)
    nearest.reason = ('FUERA DEL RECUADRO: aviso; manejo permitido' if nearest.clearance < -5
                      else 'Dentro del recuadro; manejo permitido hasta el borde')
    return nearest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostico')
    parser.add_argument('--mejora-ia', action='store_true', help='Superresolucion x2 solo en la vista ampliada')
    parser.add_argument('--zoom', type=float, default=1., help='Zoom digital inicial entre 1 y 4')
    parser.add_argument('--dashboard-port', type=int, default=8765)
    parser.add_argument('--sin-dashboard', action='store_true')
    parser.add_argument('--n8n', default=None, metavar='URL',
                        help='Webhook de n8n que apunta cada residuo separado (por defecto el de n8n en este Mac)')
    parser.add_argument('--sin-n8n', action='store_true', help='No enviar los residuos separados a n8n')
    parser.add_argument('--conectar', action='store_true')
    parser.add_argument('--solo-vision', action='store_true',help='Detectar residuos sin conectar el robot')
    parser.add_argument('--modelo',default=str(Path(__file__).resolve().parent/'models/residuos-world-small.pt'))
    parser.add_argument('--clases',default=None)
    parser.add_argument('--nombre', default=NOMBRE)
    parser.add_argument('--velocidad-max', type=float, default=100)
    parser.add_argument('--margen', type=float, default=20)
    parser.add_argument('--camara', type=camera_arg,
                        help='Nombre (lifecam, samsung, camo) o numero de una camara externa; sin esto se elige la unica reconocida')
    parser.add_argument('--resolucion', type=size_arg,
                        help='Captura ANCHOxALTO, p. ej. 1920x1080. El analisis sigue a 640 px de lado mayor')
    parser.add_argument('--listar-camaras', action='store_true', help='Mostrar las camaras que ve el Mac y salir')
    parser.add_argument('--modelo-propio', default=str(Path(__file__).resolve().parent/'models/residuos-propio.pt'),
                        help='Detector entrenado con tus residuos (entrenar_detector.py); se usa si existe')
    parser.add_argument('--sin-modelo-propio', action='store_true', help='No usar el detector entrenado')
    parser.add_argument('--otros-residuos', action='store_true',
                        help='Usar tambien los detectores generales (YOLO-World, Grounding DINO): mas tipos de residuo, pero '
                             'muchas mas confusiones. Por defecto, si el detector propio conoce la lata, solo se usan sus residuos')
    parser.add_argument('--modelo-robot', default=str(Path(__file__).resolve().parent/'models/robot-propio.pt'),
                        help='Detector entrenado con el robot (si falta, se busca con Grounding DINO)')
    parser.add_argument('--sin-modelo-robot', action='store_true', help='Buscar el robot solo con Grounding DINO')
    args = parser.parse_args()
    if args.listar_camaras:
        print('\n'.join(describe()) or 'El Mac no ve ninguna camara.')
        return
    if not np.isfinite(args.velocidad_max) or args.velocidad_max <= 0 or not np.isfinite(args.margen) or args.margen < 0:
        parser.error('Velocidad positiva y margen no negativo.')
    if not np.isfinite(args.zoom) or not 1 <= args.zoom <= 4:
        parser.error('Zoom entre 1 y 4.')
    enhancer = SuperResolution(args.mejora_ia)
    zoom = InspectionZoom(max(2.,args.zoom) if args.mejora_ia else args.zoom, enhancer)
    diagnostic = Path(args.diagnostico) if args.diagnostico else None
    if diagnostic:
        diagnostic.mkdir(parents=True, exist_ok=True)
    store = EventStore()
    counter = SeparationCounter(store)
    # Cada residuo separado, también a n8n (hoja de cálculo). Sin n8n abierto se reintenta solo; nunca frena al robot.
    n8n = None if args.sin_n8n else N8nSender(args.n8n or N8N_URL)
    if n8n is not None:
        store.listeners.append(n8n.send)
    server = None
    video = LiveVideo()
    if not args.sin_dashboard:
        try:
            server = serve(store, args.dashboard_port, video)
            print(f'Dashboard: http://127.0.0.1:{server.server_port}', flush=True)
        except OSError as exc:
            print('Dashboard: puerto ocupado. Si el panel ya está abierto, recibirá estos datos. '+str(exc), flush=True)
    try:
        camera = Camera(args.camara, args.resolucion)
    except Exception:
        store.publish({'session':counter.session,'updated':time.time(),'running':False})
        if n8n is not None:
            n8n.close()
        if server:
            server.shutdown()
            server.server_close()
        raise
    waste = WasteDetector(camera,args.modelo,[c.strip() for c in args.clases.split(',') if c.strip()] if args.clases else None, focus=zoom,
                          custom=None if args.sin_modelo_propio else args.modelo_propio,
                          robot=None if args.sin_modelo_robot or args.solo_vision else args.modelo_robot,
                          generic=True if args.otros_residuos else None)
    paper = PaperDetector(camera, focus=zoom)
    state = CommandState()
    guard = BluetoothGuard(state, args.nombre)
    window = 'Ranger | Residuos automaticos' if args.solo_vision else 'Ranger | Linea y robot sin etiqueta'
    reference = tracker = box = side = initial_hist = None
    boundary = None
    automatic = AutoBoundary()
    initial_area = 0
    initial_radius = 0
    armed, command, until = False, 'x', 0
    last_stamp = last_saved = 0
    last_report = last_video = loops = 0
    exit_since = None
    exit_frame = None
    outside = False
    previous = None
    speeds = []
    moving_since = None
    work_shape = getattr(camera, 'work_shape', (480,640,3))
    camera_text = getattr(camera, 'summary', lambda: camera.name)
    ignore_zone = getattr(camera, 'ignore_zone', None)
    notice = 'Recuadro automatico. El robot se busca solo (R: elegirlo con el raton).'
    nav = GoToWaste()
    # Hojas de color donde se llevan los residuos (amarilla: aprovechables; roja: peligrosos). Se recuerdan en el recuadro.
    sheets = vision_hojas.Sheets()
    beep_until = 0
    robot_stamp, robot_seen = 0, None

    def track_robot(image, rect):
        """Empieza a seguir el cuerpo del robot (elegido con R o encontrado solo)."""
        nonlocal tracker, box, initial_hist, initial_area, initial_radius, side, previous, speeds
        hist = appearance(image, rect)
        tracker = box = None
        if hist is None:
            return False
        tracker = cv2.TrackerCSRT_create()
        tracker.init(image, rect)
        box = tuple(map(int, rect))
        initial_hist, initial_area = hist, box[2]*box[3]
        initial_radius = np.hypot(box[2], box[3])*.575
        if reference is not None:
            a, n = line_normal(reference)
            side = 1 if (np.array([box[0]+box[2]/2, box[1]+box[3]/2])-a) @ n >= 0 else -1
        previous, speeds = None, []
        return True
    try:
        cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        cv2.createTrackbar('Contraste', window, 30, 100, lambda _: None)
        cv2.setMouseCallback(window, zoom.mouse)
        if args.conectar and not args.solo_vision:
            guard.start()
        loop_ms = 0.
        while True:
            loop_start = time.monotonic()
            sample = detail_sample(camera)
            frame, full, stamp = sample if sample else (np.zeros(work_shape,np.uint8), None, 0)
            detection = tape_image(frame)
            # Las líneas sueltas solo hacen falta para el modo de una línea y para elegir con B antes de tener
            # recuadro; con recuadro se sigue con la cinta medida en su sitio y el bucle va más rápido.
            lines = (black_lines(detection, max(10,cv2.getTrackbarPos('Contraste',window)))
                     if time.monotonic()-stamp < .3 and (reference is not None or automatic.boundary is None) else [])
            # El robot no puede formar parte del recuadro: se excluye su caja de la imagen anterior.
            robot_area = [(box[0],box[1],box[0]+box[2],box[1]+box[3])] if box is not None else []
            # Con el recuadro ya confirmado y visible, la búsqueda completa basta una imagen de cada tres: entre medias
            # se comprueba la cinta en su sitio (mucho más rápido) y el bucle no se retrasa.
            loops += 1
            search = automatic.boundary is None or not automatic.visible or loops % 3 == 0
            quads = tape_squares(frame,robot_area) if time.monotonic()-stamp < .3 and search else []
            candidate = quads[0] if quads else None
            if reference is None:
                if automatic.update(quads,lines,stamp,time.monotonic(),seen=lambda quad:square_support(frame,quad)):
                    armed,command,until = False,'x',0
                    state.set()
                    if boundary is not None:
                        # La cámara se movió: se detiene, pero el robot se sigue igual (su detector lo corrige).
                        notice = 'Recuadro reubicado automaticamente. Pulsa E y G para seguir.'
                    else:
                        notice = 'Recuadro seleccionado automaticamente. Buscando el robot.'
                boundary = automatic.boundary
            visible = (automatic.visible if boundary is not None
                       else reference is not None and matching_line(reference, lines) is not None)
            # El robot lo busca su detector propio en cada análisis; sin él, Grounding DINO cada dos análisis.
            own_finder = getattr(waste, 'robot_ready', False)
            hits, hit_stamp, hit_frame = (tuple(getattr(waste if own_finder else paper, 'robot', ([], 0))) + (None,))[:3]
            lost_now = False
            if tracker is not None and stamp != last_stamp:
                ok, tracked = tracker.update(frame)
                hist = appearance(frame, tracked) if ok else None
                area = tracked[2]*tracked[3] if ok else 0
                if hist is None or not .65*initial_area < area < 1.5*initial_area or cv2.compareHist(initial_hist,hist,cv2.HISTCMP_CORREL) < .55:
                    tracker = box = None
                    lost_now = True
                    notice = 'Seguimiento perdido. Detenido. Buscando el robot de nuevo (o R).'
                else:
                    box = tuple(map(int,tracked))
                    center = np.array([box[0]+box[2]/2,box[1]+box[3]/2])
                    if previous is not None and 0 < stamp-previous[1] < .3:
                        speeds.append((time.monotonic(), float(np.linalg.norm(center-previous[0])/(stamp-previous[1]))))
                    previous = (center,stamp)
            last_stamp = stamp
            # Sin etiqueta ni ratón: mientras no se sigue al robot, el detector lo busca. Se empieza a seguir
            # cuando aparece en el mismo sitio en dos análisis seguidos, dentro o junto al recuadro.
            paper.want_robot = not args.solo_vision and tracker is None and not own_finder
            # Con el detector entrenado con caja y lata, los generales se apagan (salvo --otros-residuos).
            paper.want_waste = getattr(waste, 'generic', True) is not False
            # Un análisis nuevo; o, si el seguimiento acaba de fallar, el último si es de hace menos de medio segundo.
            new_hit = hit_stamp != robot_stamp or (lost_now and time.monotonic()-hit_stamp < .5)
            if not args.solo_vision and new_hit and hits and time.monotonic()-stamp < .3:
                robot_stamp = hit_stamp
                near = [(b, score) for b, score in hits if boundary is None or
                        cv2.pointPolygonTest(np.float32(boundary), (float((b[0]+b[2])/2), float((b[1]+b[3])/2)), True) > -40]
                if tracker is not None:
                    # Ya seguido: si el seguimiento se ha ido desplazando (otra caja muy distinta), se corrige con el
                    # detector propio. Al empujar un residuo, CSRT tiende a quedarse en él.
                    if own_finder and near and near[0][1] >= .6 and overlap(near[0][0], (box[0],box[1],box[0]+box[2],box[1]+box[3])) < .4:
                        x1, y1, x2, y2 = map(int, near[0][0])
                        source = hit_frame if hit_frame is not None and hit_frame.shape == frame.shape else frame
                        if track_robot(source, (x1, y1, x2-x1, y2-y1)):
                            ok, tracked = tracker.update(frame)
                            if ok:
                                box = tuple(map(int, tracked))
                # Detector propio: basta un análisis con 0,5. DINO: 0,6 (se midió 0,50-0,85) o repetido en el mismo sitio.
                elif near and (near[0][1] >= (.5 if own_finder else .6) or
                               (robot_seen is not None and overlap(near[0][0], robot_seen) > .3)):
                    x1, y1, x2, y2 = map(int, near[0][0])
                    # La caja es de la imagen analizada, quizá de hace un segundo: el seguimiento empieza en esa
                    # imagen y la lleva a la actual (la cámara en la mano puede haberse movido).
                    source = hit_frame if hit_frame is not None and hit_frame.shape == frame.shape else frame
                    if track_robot(source, (x1, y1, x2-x1, y2-y1)):
                        ok, tracked = tracker.update(frame)
                        if ok:
                            box = tuple(map(int, tracked))
                        notice = 'Robot encontrado automaticamente. C: conectar; E: habilitar; G: separar residuos.'
                    robot_seen = None
                else:
                    robot_seen = near[0][0] if near else None
            now = time.monotonic()
            speeds = [(t,v) for t,v in speeds if now-t < 1]
            speed = max(args.velocidad_max,max((v for _,v in speeds),default=0))
            decision = (assess_rectangle(boundary,visible,box,now-stamp,speed,0)
                        if boundary is not None else
                        assess_line(reference,visible,box,side,now-stamp,speed,0))
            crossing = decision.safe and decision.clearance is not None and decision.clearance < -5
            if crossing:
                if exit_since is None:
                    exit_since, exit_frame = now, stamp
                outside = now-exit_since >= .25 and stamp != exit_frame
            else:
                exit_since = exit_frame = None
                outside = False
            # En marcha, una imagen real cambia. Una cámara virtual puede repetir la última si se
            # corta el teléfono: tras 0,6 s de pasos sin ningún cambio se detiene el robot.
            stepping = armed and command in 'wasd' and now < until+.3
            moving_since = (moving_since or now) if stepping else None
            if frozen_while_moving(moving_since,getattr(camera,'changed',now),now):
                armed, command, until, moving_since = False, 'x', 0, None
                notice = 'Imagen sin cambios con el robot en marcha: detenido. Revisa la camara.'
            if not decision.safe or not guard.connected:
                armed, command, until = False, 'x', 0
            state.set(decision.safe,armed,command,until,outside)
            view = frame.copy()
            if boundary is not None:
                cv2.polylines(view,[boundary.astype(int)],True,(0,255,0) if visible else (0,160,255),3)
            elif reference is not None:
                cv2.line(view,tuple(reference[:2]),tuple(reference[2:]),(0,255,0) if visible else (0,0,255),3)
            else:
                for line in lines:
                    cv2.line(view,tuple(line[:2]),tuple(line[2:]),(0,220,255),2)
                if candidate is not None:
                    cv2.polylines(view,[candidate.astype(int)],True,(0,220,255),3)
            if box is not None:
                x,y,w,h = box
                cv2.rectangle(view,(x,y),(x+w,y+h),(255,200,0),2)
                cv2.putText(view,'RANGER',(x,max(16,y-5)),cv2.FONT_HERSHEY_SIMPLEX,.5,(255,200,0),2)
            waste_boxes,waste_stamp = waste.latest_details
            observations=[]
            if now-waste_stamp < 1:
                observations=outside_zone([(b,n,c,a+now-waste_stamp) for b,n,c,a in waste_boxes
                                           if not n.startswith('papel')],ignore_zone,frame.shape)
            if now-stamp < .3:
                special=[(b,n,c,a+now-stamp) for b,n,c,a in paper.read(frame,stamp)]
                observations=merge_observations(observations,outside_zone(special,ignore_zone,frame.shape))
            own_boxes,own_stamp = getattr(waste,'custom_details',([],0))
            if now-own_stamp < 1:
                # El detector entrenado con estos residuos tiene prioridad sobre los genéricos donde coinciden.
                own=[(b,n,c,a+now-own_stamp) for b,n,c,a in own_boxes]
                observations=merge_observations(observations,outside_zone(own,ignore_zone,frame.shape))
            objects = []
            if boundary is not None and visible and now-stamp < .3 and (loops % 3 == 0 or not sheets.known):
                sheets.update(frame,boundary,now)
            sheets_image = sheets.in_image(boundary) if boundary is not None and sheets.known else {}
            for color,quad in sheets_image.items():
                cv2.polylines(view,[np.int32(np.round(quad))],True,vision_hojas.COLORES[color],2)
                which = vision_hojas.GRUPO.get(color, color)
                cv2.putText(view,which,tuple(int(v) for v in quad.min(axis=0)-[0,4]),cv2.FONT_HERSHEY_SIMPLEX,.4,
                            vision_hojas.COLORES[color],1,cv2.LINE_AA)
            # Clase -> hoja (en el plano del recuadro), para el robot y el conteo.
            goals = {label: sheets.known[color] for label,color in vision_hojas.DESTINO.items() if color in sheets.known}
            waste.zones = {label: sheets_image[color] for label,color in vision_hojas.DESTINO.items() if color in sheets_image}
            robot_boxes = [(box[0],box[1],box[0]+box[2],box[1]+box[3])] if box is not None else []
            if own_finder and hits and now-hit_stamp < 1 and hits[0][1] >= .5:
                robot_boxes.append(tuple(hits[0][0]))
            if now-stamp < .3:
                for coordinates,name,confidence,observation_age in sorted(observations,key=lambda o:-o[2]):
                    x1,y1,x2,y2 = map(int,coordinates)
                    center=((x1+x2)/2,(y1+y2)/2)
                    # El robot no es un residuo: fuera lo que cae sobre él (su caja seguida o la última detectada).
                    if any(covered((x1,y1,x2,y2),r) > .5 or r[0] <= center[0] <= r[2] and r[1] <= center[1] <= r[3]
                           for r in robot_boxes):
                        continue
                    # La hoja roja se tomaba por una caja (sola o junto con la caja de encima): si la detección abarca
                    # la hoja, se recorta a lo que hay encima de ella; si no hay nada, se descarta.
                    if sheets_image and vision_hojas.on_sheet((x1,y1,x2,y2),sheets_image,frame) is None:
                        continue
                    # Dos detecciones del mismo residuo (la caja sola y la caja con la hoja de debajo): se queda la
                    # ajustada; la grande que la contiene sobra.
                    same = [o for o in observations if o is not None and o[1] == name and o[0] is not coordinates]
                    area = max((x2-x1)*(y2-y1),1)
                    if any(vision_hojas.inside_of(o[0],(x1,y1,x2,y2)) > .75 and area > 1.3*vision_hojas.area_of(o[0])
                           for o in same):
                        continue
                    if any(o['label'] == {'bottle':'botella','cup':'vaso/taza'}.get(name,name) and
                           overlap((x1,y1,x2,y2),o['box']) > .5 for o in objects):
                        continue
                    label={'bottle':'botella','cup':'vaso/taza'}.get(name,name)
                    inside=(bool(cv2.pointPolygonTest(boundary,center,False)>=0)
                            if boundary is not None and visible else None)
                    countable=name!='objeto por identificar'
                    # Ya en su hoja (separado): el panel no lo cuenta como pendiente.
                    goal_color=vision_hojas.DESTINO.get(label)
                    on_goal=bool(goal_color in sheets_image and
                                 (cv2.pointPolygonTest(np.float32(sheets_image[goal_color]),center,False) >= 0 or
                                  vision_hojas.share_on([[x1,y1],[x2,y1],[x2,y2],[x1,y2]],sheets_image[goal_color]) >= vision_hojas.ON_SHEET))
                    color=(230,80,240) if countable else (0,210,255)
                    objects.append({'countable':countable,'type':name,'label':label,'confidence':float(confidence),
                                    'box':[x1,y1,x2,y2],'center':list(center),'inside':inside,
                                    'observation_age':float(observation_age),'sorted':on_goal})
                    cv2.rectangle(view,(x1,y1),(x2,y2),color,2)
                    cv2.circle(view,(int(center[0]),int(center[1])),4,color,-1)
                    caption=f'{label} {confidence:.0%}'+(' (seguimiento)' if observation_age>.7 else '')
                    text_width=cv2.getTextSize(caption,cv2.FONT_HERSHEY_SIMPLEX,.43,1)[0][0]
                    text_x=max(2,min(x1,frame.shape[1]-text_width-3))
                    cv2.putText(view,caption,(text_x,max(16,y1-6)),
                                cv2.FONT_HERSHEY_SIMPLEX,.43,color,1,cv2.LINE_AA)
            countable_objects=[o for o in objects if o['countable']]
            if nav.pushed_out is not None:
                counter.pushed_out(*nav.pushed_out); nav.pushed_out = None
            counter.update(objects,boundary,visible and now-stamp < .3,now,shape=frame.shape,
                           robot=[box[0],box[1],box[0]+box[2],box[1]+box[3]] if box is not None else None,sheets=goals)
            nav.sheets = goals
            if nav.active:
                if not decision.safe or not armed or not guard.connected:
                    nav.stop('Automatico detenido: '+(decision.reason if not decision.safe else 'robot no habilitado o sin conexion'))
                else:
                    # Si sale del recuadro no se para: el propio automático lo devuelve dentro (pedido del usuario:
                    # pararlo fuera obligaba a ir a buscarlo).
                    # Posiciones medidas respecto al recuadro: si la cámara se mueve (en la mano), el recuadro
                    # se mueve con ella y el desplazamiento medido sigue siendo solo el del robot.
                    plane = None
                    if boundary is not None:
                        square = cv2.getPerspectiveTransform(np.float32(boundary),np.float32([[0,0],[400,0],[400,400],[0,400]]))
                        plane = lambda pts,m=square: cv2.perspectiveTransform(np.float32(pts).reshape(-1,1,2),m).reshape(-1,2)
                    # Para medir cuánto y hacia dónde se movió, la caja del detector del robot tiembla mucho menos que
                    # la del seguimiento (que además salta cuando se corrige). Se usa si es reciente y coincide.
                    nav_box, nav_stamp, nav_frame = box, stamp, frame
                    if own_finder and hits and now-hit_stamp < .5 and box is not None and \
                            overlap(hits[0][0], (box[0],box[1],box[0]+box[2],box[1]+box[3])) > .2:
                        x1, y1, x2, y2 = hits[0][0]
                        nav_box, nav_stamp = (x1, y1, x2-x1, y2-y1), hit_stamp
                        if hit_frame is not None and hit_frame.shape == frame.shape:
                            nav_frame = hit_frame
                    # Hacia dónde mira, por sus orugas en la misma imagen que la caja (2/11): evita casi todos los pasos
                    # de comprobación tras cada giro, que con la caja temblando medían con ~20° de error.
                    nav_axis = None
                    if nav_box is not None and plane is not None:
                        seen = track_axis(nav_frame, nav_box)
                        nav_axis = plane_axis(seen, nav_box, plane) if seen is not None else None
                    step = nav.update(now,nav_stamp,nav_box,objects,plane,nav_axis)
                    if step:
                        command,until = step[0],now+step[1]
                    if nav.beep:
                        # Al llegar, al sacar cada residuo y al dejar el recuadro limpio.
                        nav.beep = False
                        beep_until = now+.3
                if not nav.active:
                    command,until = 'x',0
            if nav.active and nav.plan and boundary is not None:
                # La línea que sigue el robot: desde él (círculo), por el residuo, hasta donde cruzará la cinta.
                back = cv2.getPerspectiveTransform(np.float32([[0,0],[400,0],[400,400],[0,400]]),np.float32(boundary))
                start,through,goal = cv2.perspectiveTransform(np.float32([nav.plan['robot'],nav.plan['waste'],nav.plan['exit']]).reshape(-1,1,2),back).reshape(-1,2).astype(int)
                if box is not None:
                    start = np.array([box[0]+box[2]//2,box[1]+box[3]//2])
                cv2.circle(view,tuple(int(v) for v in start),7,(255,255,0),2)
                if nav.plan.get('staging') is not None:
                    # Llevándolo a su hoja: primero se coloca detrás del residuo (punto pequeño).
                    stage = cv2.perspectiveTransform(np.float32([nav.plan['staging']]).reshape(-1,1,2),back).reshape(2).astype(int)
                    cv2.line(view,tuple(int(v) for v in start),tuple(stage),(255,255,0),1,cv2.LINE_AA)
                    cv2.circle(view,tuple(stage),4,(255,255,0),-1)
                    start = stage
                cv2.line(view,tuple(int(v) for v in start),tuple(through),(255,255,0),2,cv2.LINE_AA)
                cv2.circle(view,tuple(through),12,(255,255,0),2)
                cv2.arrowedLine(view,tuple(through),tuple(goal),(0,200,255),2,tipLength=.08)
            if nav.active and box is not None:
                cx,cy = box[0]+box[2]//2,box[1]+box[3]//2
                if nav.heading is not None:
                    ahead = np.array([math.cos(math.radians(nav.heading)),math.sin(math.radians(nav.heading))])
                    tip = (cx+int(35*ahead[0]),cy+int(35*ahead[1]))
                    if boundary is not None:
                        # El rumbo se mide en el plano del recuadro: se dibuja llevándolo a la imagen.
                        square = cv2.getPerspectiveTransform(np.float32(boundary),np.float32([[0,0],[400,0],[400,400],[0,400]]))
                        start = cv2.perspectiveTransform(np.float32([[[cx,cy]]]),square)[0,0]
                        end = cv2.perspectiveTransform(np.float32([[start+30*ahead]]),np.linalg.inv(square))[0,0]
                        tip = (int(end[0]),int(end[1]))
                    cv2.arrowedLine(view,(cx,cy),tip,(0,255,255),2,tipLength=.3)
            panel = np.full((195 if args.solo_vision else 219,frame.shape[1],3),24,np.uint8)
            distance = f'Distancia al borde: {decision.clearance:.0f}px | Cruzar no frena el robot' if decision.clearance is not None else 'Recuadro automatico; R para seleccionar el robot.'
            border_status = decision.reason
            if boundary is None and reference is None:
                border_status = ('RECUADRO: estabilizando seleccion automatica...' if candidate is not None
                                 else f'Lineas detectadas: {len(lines)} - buscando recuadro')
            elif boundary is not None and not visible:
                border_status = 'Borde conservado; esperando cinta visible. Robot detenido.'
            elif boundary is not None and box is None:
                border_status = 'RECUADRO SELECCIONADO AUTOMATICAMENTE - R: robot'
            rows = [border_status,guard.status,distance,
                    'Movimiento: '+('HABILITADO' if armed else 'BLOQUEADO'),
                    'Cinta automatica | R: robot | C: Bluetooth | E: habilitar | G: separar residuos',
                    'T: reiniciar cinta | N: reiniciar todo | Espacio: parar | Q: salir',
                    notice,'Camara: '+camera_text()]
            if args.solo_vision:
                zone_status=('Recuadro automatico activo' if boundary is not None and visible
                             else 'Buscando recuadro; deteccion de objetos activa')
                rows=[f'POSIBLES RESIDUOS: {len(countable_objects)} | Por identificar: {len(objects)-len(countable_objects)}',
                      'Envases, latas, papel, carton, bolsas y restos de comida',
                      zone_status,'Morado: posible residuo | Amarillo: por identificar (no se cuenta)',
                      waste.status+' | '+paper.status,'T: reiniciar recuadro | Q: salir',
                      enhancer.status,'Camara: '+camera_text()]
            else:
                rows[3]+=f' | Posibles residuos: {len(countable_objects)}'
                rows[6]=waste.status
                rows.append(nav.message)
            if now-last_report >= .5:
                last_report = now
                store.publish({'session':counter.session,'updated':time.time(),'running':True,
                    'boundary':boundary.tolist() if boundary is not None else None,'visible':bool(visible),
                    'robot_box':list(box) if box is not None else None,'objects':countable_objects,
                    'frame_size':[int(frame.shape[1]),int(frame.shape[0])],
                    'unclassified_objects':[o for o in objects if not o['countable']],
                    'outside':bool(outside),'camera_age':float(now-stamp),'sorting':sorted(sheets.known),'connected':bool(guard.connected),'border_status':border_status,
                    'bluetooth':guard.status,'waste_status':waste.status,'paper_status':paper.status,
                    'n8n_status':n8n.status if n8n is not None else 'n8n apagado',
                    'n8n':n8n.summary() if n8n is not None else None})
            for i,row in enumerate(rows):
                color = (80,240,80) if i == 0 and decision.safe else ((80,80,255) if i == 0 else (230,230,230))
                if args.solo_vision and i == 0:
                    color = (80,240,80) if objects else (230,230,230)
                cv2.putText(panel,row[:92],(10,21+i*24),cv2.FONT_HERSHEY_SIMPLEX,.40,color,1,cv2.LINE_AA)
            if video.wanted() and now-last_video >= .1:
                # La imagen con las marcas, sin zoom ni panel, para el panel web (hasta 10 por segundo).
                last_video = now
                ok, jpeg = cv2.imencode('.jpg',view,[cv2.IMWRITE_JPEG_QUALITY,80])
                if ok:
                    video.publish(jpeg.tobytes())
            view = np.vstack([zoom.render(view,full,frame),panel])
            cv2.imshow(window,view)
            if diagnostic and now-last_saved > 1:
                cv2.imwrite(str(diagnostic/'camara.jpg'),frame)
                cv2.imwrite(str(diagnostic/'vista.jpg'),view)
                (diagnostic/'estado.json').write_text(json.dumps({
                    'time':time.time(),'camera':camera_text(),
                    'camera_size':list(getattr(camera,'size',frame.shape[1::-1])),
                    'analysis_size':[int(frame.shape[1]),int(frame.shape[0])],
                    'loop_ms':loop_ms,'image_age_ms':1000*(time.monotonic()-stamp),
                    'boundary':boundary.tolist() if boundary is not None else None,
                    'tracks':[{'id':t['id'],'label':t['label'],'zone':t['zone'],'inside':t['inside'],'counted':t['counted'],
                               'center':[round(float(v),1) for v in t['center']],'unseen':round(now-t['seen'],1)}
                              for t in counter.tracks if 'center' in t],
                    'unchanged_seconds':time.monotonic()-getattr(camera,'changed',time.monotonic()),'line_confirmed':reference is not None or boundary is not None,
                    'detected_lines':len(lines),'rectangle_detected':candidate is not None,
                    'rectangle_confirmed':boundary is not None,'border_message':border_status,
                    'line_visible':bool(visible),'robot_box':box,'safe':decision.safe,
                    'message':decision.reason,'bluetooth':guard.status,'armed':armed,
                    'waste_status':waste.status,'paper_status':paper.status,
                    'n8n_status':n8n.status if n8n is not None else 'n8n apagado',
                    'detector_age':now-waste_stamp,
                    'zoom':zoom.level,'zoom_region':zoom.region(frame.shape),
                    'superres_enabled':enhancer.enabled,'superres_status':enhancer.status,
                    'superres_ms':enhancer.elapsed_ms,
                    'auto_active':nav.active,'auto_message':nav.message,'auto_heading':nav.heading,
                    'auto_turn_rate':nav.turn_rate,'auto_speed':nav.speed,'auto_axis':nav.axis,
                    'objects':objects,'vision_only':args.solo_vision},indent=2),encoding='utf-8')
                last_saved = now
            key = cv2.waitKey(15)&0xff
            loop_ms = 1000*(time.monotonic()-loop_start)
            if key == ord('q') or cv2.getWindowProperty(window,cv2.WND_PROP_VISIBLE) < 1:
                break
            if zoom.key(key):
                pass
            elif key in (ord(' '),ord('x')):
                armed,command,until = False,'x',0
                if nav.active:
                    nav.stop('Automatico detenido por el usuario')
            elif key == ord('g') and not args.solo_vision:
                if nav.active:
                    nav.stop('Automatico detenido por el usuario')
                    command,until = 'x',0
                elif not (armed and guard.connected and decision.safe):
                    notice = 'Para G: selecciona el robot (R), conecta (C) y habilita (E).'
                else:
                    nav.start(now)
                    notice = 'Automatico: lleva cada residuo a su hoja (o fuera si no tiene). Espacio: parar.'
            elif key == ord('c') and not args.solo_vision:
                guard.start()
            elif key in (ord('b'),ord('r'),ord('n'),ord('t')):
                armed,command,until = False,'x',0
                if nav.active:
                    nav.stop('Automatico detenido: se reinicio la seleccion')
                state.set()
                exit_since = exit_frame = None
                outside = False
                if key in (ord('n'),ord('t'),ord('b')):
                    counter.reset_zone()
                if key == ord('n'):
                    reference = tracker = box = side = None
                    boundary = None
                    automatic.reset()
                    sheets.reset()
                    notice = 'Todo reiniciado. Buscando recuadro automaticamente.'
                elif key == ord('t'):
                    reference = side = None
                    boundary = None
                    automatic.reset()
                    sheets.reset()
                    notice = 'Cinta borrada. Buscando de nuevo. Robot conservado.'
                elif key == ord('b'):
                    if candidate is not None and time.monotonic()-stamp < .3:
                        boundary = candidate.copy()
                        automatic.confirm(boundary,stamp)
                        reference = side = None
                        notice = '4 lados confirmados. R: robot; E: habilitar; W/A/S/D: pasos.'
                    elif len(lines) == 1 and time.monotonic()-stamp < .3:
                        boundary = None
                        automatic.reset()
                        reference = lines[0].copy()
                        side = None
                        if box is not None:
                            a,n = line_normal(reference)
                            center = np.array([box[0]+box[2]/2,box[1]+box[3]/2])
                            side = 1 if (center-a) @ n >= 0 else -1
                        notice = 'Cinta confirmada. R: robot; E: habilitar; W/A/S/D: pasos.'
                    else:
                        notice = 'Recuadro incompleto. Muestra los 4 lados para confirmar.'
                elif not args.solo_vision and (reference is not None or boundary is not None) and visible and time.monotonic()-stamp < .3:
                    selected = cv2.selectROI('Selecciona TODO el Ranger y pulsa Enter',frame,False,False)
                    cv2.destroyWindow('Selecciona TODO el Ranger y pulsa Enter')
                    if track_robot(frame,selected):
                        notice = 'Verifica el recuadro azul sobre el robot. C: conectar.'
            elif key == ord('e') and decision.safe and guard.connected:
                armed = True
            elif key in map(ord,'wasd') and armed and decision.safe:
                if nav.active:
                    nav.stop('Automatico detenido: control manual')
                command,until = chr(key),time.monotonic()+.15
            # Tras una seleccion modal la imagen anterior no autoriza movimientos.
            if time.monotonic()-stamp > .3:
                state.set()
            else:
                # El pitido de llegada reutiliza el aviso del firmware («p»), que no detiene motores.
                state.set(decision.safe,armed,command,until,outside or now < beep_until)
    finally:
        state.set()
        guard.close()
        waste.stop.set()
        paper.stop.set()
        camera.close()
        cv2.destroyAllWindows()
        store.publish({'session':counter.session,'updated':time.time(),'running':False})
        if n8n is not None:
            n8n.close()
        if server:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit('Error: '+str(exc))
