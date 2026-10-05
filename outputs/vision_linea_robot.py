#!/usr/bin/env python3
"""Prueba supervisada de cinta o recuadro y Ranger seleccionado, sin etiqueta."""
import argparse
import json
from pathlib import Path
import time
import cv2
import numpy as np
from vision_core import black_lines, black_enclosures, same_boundary, Decision
from vision_ranger import Camera, CommandState, BluetoothGuard, WasteDetector
from ranger_bluetooth import NOMBRE
from vision_boundary import AutoBoundary, tape_image
from vision_papel import PaperDetector


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
    required = margin + speed*(1.25+age)
    if clearance <= required:
        return Decision(False, 'CERCA DE LA LINEA: parada y alarma', clearance, required)
    return Decision(True, 'Robot separado de la linea', clearance, required)


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
    nearest.reason = ('Robot separado de los 4 lados' if nearest.safe
                      else 'CERCA DEL BORDE: parada y alarma')
    return nearest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostico')
    parser.add_argument('--conectar', action='store_true')
    parser.add_argument('--solo-vision', action='store_true',help='Detectar residuos sin conectar el robot')
    parser.add_argument('--modelo',default=str(Path(__file__).resolve().parent/'models/residuos-world-small.pt'))
    parser.add_argument('--clases',default=None)
    parser.add_argument('--nombre', default=NOMBRE)
    parser.add_argument('--velocidad-max', type=float, default=100)
    parser.add_argument('--margen', type=float, default=20)
    args = parser.parse_args()
    if not np.isfinite(args.velocidad_max) or args.velocidad_max <= 0 or not np.isfinite(args.margen) or args.margen < 0:
        parser.error('Velocidad positiva y margen no negativo.')
    diagnostic = Path(args.diagnostico) if args.diagnostico else None
    if diagnostic:
        diagnostic.mkdir(parents=True, exist_ok=True)
    camera = Camera()
    waste = WasteDetector(camera,args.modelo,[c.strip() for c in args.clases.split(',') if c.strip()] if args.clases else None)
    paper = PaperDetector(camera)
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
    previous = None
    speeds = []
    notice = 'Recuadro automatico. R: encerrar TODO el robot con el raton.'
    try:
        cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
        cv2.createTrackbar('Contraste', window, 30, 100, lambda _: None)
        if args.conectar and not args.solo_vision:
            guard.start()
        while True:
            sample = camera.read()
            frame, stamp = sample if sample else (np.zeros((480,640,3),np.uint8), 0)
            detection = tape_image(frame)
            lines = black_lines(detection, max(10,cv2.getTrackbarPos('Contraste',window))) if time.monotonic()-stamp < .3 else []
            quads = black_enclosures(detection) if time.monotonic()-stamp < .3 else []
            candidate = quads[0] if quads else None
            if reference is None:
                if automatic.update(quads,lines,stamp,time.monotonic()):
                    armed,command,until = False,'x',0
                    state.set()
                    if boundary is not None:
                        tracker = box = None
                        notice = 'Recuadro reubicado automaticamente. R: selecciona el robot.'
                    else:
                        notice = 'Recuadro seleccionado automaticamente. R: selecciona el robot.'
                boundary = automatic.boundary
            visible = (automatic.visible if boundary is not None
                       else reference is not None and matching_line(reference, lines) is not None)
            if tracker is not None and stamp != last_stamp:
                ok, tracked = tracker.update(frame)
                hist = appearance(frame, tracked) if ok else None
                area = tracked[2]*tracked[3] if ok else 0
                if hist is None or not .65*initial_area < area < 1.5*initial_area or cv2.compareHist(initial_hist,hist,cv2.HISTCMP_CORREL) < .55:
                    tracker = box = None
                    notice = 'Seguimiento perdido. Detenido. Vuelve a seleccionar con R.'
                else:
                    box = tuple(map(int,tracked))
                    center = np.array([box[0]+box[2]/2,box[1]+box[3]/2])
                    if previous is not None and 0 < stamp-previous[1] < .3:
                        speeds.append((time.monotonic(), float(np.linalg.norm(center-previous[0])/(stamp-previous[1]))))
                    previous = (center,stamp)
            last_stamp = stamp
            now = time.monotonic()
            speeds = [(t,v) for t,v in speeds if now-t < 1]
            speed = max(args.velocidad_max,max((v for _,v in speeds),default=0))
            safety_box = None
            if box is not None:
                # Incluye las esquinas del cuerpo aunque gire o el tracker reduzca la caja.
                radius = max(initial_radius, np.hypot(box[2],box[3])*.575)
                cx,cy = box[0]+box[2]/2,box[1]+box[3]/2
                safety_box = (cx-radius,cy-radius,2*radius,2*radius)
            decision = (assess_rectangle(boundary,visible,safety_box,now-stamp,speed,args.margen+automatic.tolerance)
                        if boundary is not None else
                        assess_line(reference,visible,safety_box,side,now-stamp,speed,args.margen))
            if not decision.safe or not guard.connected:
                armed, command, until = False, 'x', 0
            state.set(decision.safe,armed,command,until)
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
                observations=[(b,n,c,a+now-waste_stamp) for b,n,c,a in waste_boxes
                              if not n.startswith('papel')]
            if now-stamp < .3:
                observations.extend(paper.read(frame,stamp))
            objects = []
            if now-stamp < .3:
                for coordinates,name,confidence,observation_age in observations:
                    x1,y1,x2,y2 = map(int,coordinates)
                    center=((x1+x2)/2,(y1+y2)/2)
                    if box is not None and box[0] <= center[0] <= box[0]+box[2] and box[1] <= center[1] <= box[1]+box[3]:
                        continue
                    label={'bottle':'botella','cup':'vaso/taza'}.get(name,name)
                    inside=(bool(cv2.pointPolygonTest(boundary,center,False)>=0)
                            if boundary is not None and visible else None)
                    objects.append({'type':name,'label':label,'confidence':float(confidence),
                                    'box':[x1,y1,x2,y2],'center':list(center),'inside':inside,
                                    'observation_age':float(observation_age)})
                    cv2.rectangle(view,(x1,y1),(x2,y2),(230,80,240),2)
                    cv2.circle(view,(int(center[0]),int(center[1])),4,(230,80,240),-1)
                    caption=f'{label} {confidence:.0%}'+(' (seguimiento)' if observation_age>.7 else '')
                    text_width=cv2.getTextSize(caption,cv2.FONT_HERSHEY_SIMPLEX,.43,1)[0][0]
                    text_x=max(2,min(x1,frame.shape[1]-text_width-3))
                    cv2.putText(view,caption,(text_x,max(16,y1-6)),
                                cv2.FONT_HERSHEY_SIMPLEX,.43,(230,80,240),1,cv2.LINE_AA)
            panel = np.full((195,frame.shape[1],3),24,np.uint8)
            distance = f'Distancia del cuerpo: {decision.clearance:.0f}px | Reserva: {decision.required:.0f}px' if decision.clearance is not None else 'Recuadro automatico; R para seleccionar el robot.'
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
                    'Cinta automatica | R: robot | C: Bluetooth | E: habilitar pasos',
                    'T: reiniciar cinta | N: reiniciar todo | Espacio: parar | Q: salir',
                    notice,'Camara: '+camera.name]
            if args.solo_vision:
                zone_status=('Recuadro automatico activo' if boundary is not None and visible
                             else 'Buscando recuadro; deteccion de objetos activa')
                rows=[f'POSIBLES RESIDUOS: {len(objects)} | Deteccion automatica',
                      'Envases, latas, papel, carton, bolsas y restos de comida',
                      zone_status,'Se marcan solos en morado. No hace falta seleccionarlos.',
                      waste.status+' | '+paper.status,'T: reiniciar recuadro | Q: salir',
                      'Solo camara; robot desconectado.','Camara: '+camera.name]
            else:
                rows[3]+=f' | Posibles residuos: {len(objects)}'
                rows[6]=waste.status
            for i,row in enumerate(rows):
                color = (80,240,80) if i == 0 and decision.safe else ((80,80,255) if i == 0 else (230,230,230))
                if args.solo_vision and i == 0:
                    color = (80,240,80) if objects else (230,230,230)
                cv2.putText(panel,row[:92],(10,21+i*24),cv2.FONT_HERSHEY_SIMPLEX,.40,color,1,cv2.LINE_AA)
            view = np.vstack([view,panel])
            cv2.imshow(window,view)
            if diagnostic and now-last_saved > 1:
                cv2.imwrite(str(diagnostic/'camara.jpg'),frame)
                cv2.imwrite(str(diagnostic/'vista.jpg'),view)
                (diagnostic/'estado.json').write_text(json.dumps({
                    'time':time.time(),'camera':camera.name,'line_confirmed':reference is not None or boundary is not None,
                    'detected_lines':len(lines),'rectangle_detected':candidate is not None,
                    'rectangle_confirmed':boundary is not None,'border_message':border_status,
                    'line_visible':bool(visible),'robot_box':box,'safe':decision.safe,
                    'message':decision.reason,'bluetooth':guard.status,'armed':armed,
                    'waste_status':waste.status,'paper_status':paper.status,
                    'detector_age':now-waste_stamp,
                    'objects':objects,'vision_only':args.solo_vision},indent=2),encoding='utf-8')
                last_saved = now
            key = cv2.waitKey(15)&0xff
            if key == ord('q') or cv2.getWindowProperty(window,cv2.WND_PROP_VISIBLE) < 1:
                break
            if key in (ord(' '),ord('x')):
                armed,command,until = False,'x',0
            elif key == ord('c') and not args.solo_vision:
                guard.start()
            elif key in (ord('b'),ord('r'),ord('n'),ord('t')):
                armed,command,until = False,'x',0
                state.set()
                if key == ord('n'):
                    reference = tracker = box = side = None
                    boundary = None
                    automatic.reset()
                    notice = 'Todo reiniciado. Buscando recuadro automaticamente.'
                elif key == ord('t'):
                    reference = side = None
                    boundary = None
                    automatic.reset()
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
                    hist = appearance(frame,selected)
                    tracker = box = None
                    if hist is not None:
                        tracker = cv2.TrackerCSRT_create()
                        tracker.init(frame,selected)
                        box = tuple(map(int,selected))
                        initial_hist,initial_area = hist,box[2]*box[3]
                        initial_radius = np.hypot(box[2],box[3])*.575
                        if reference is not None:
                            a,n = line_normal(reference)
                            center = np.array([box[0]+box[2]/2,box[1]+box[3]/2])
                            side = 1 if (center-a) @ n >= 0 else -1
                        previous, speeds = None,[]
                        notice = 'Verifica el recuadro azul sobre el robot. C: conectar.'
            elif key == ord('e') and decision.safe and guard.connected:
                armed = True
            elif key in map(ord,'wasd') and armed and decision.safe:
                command,until = chr(key),time.monotonic()+.15
            # Tras una seleccion modal la imagen anterior no autoriza movimientos.
            if time.monotonic()-stamp > .3:
                state.set()
            else:
                state.set(decision.safe,armed,command,until)
    finally:
        state.set()
        guard.close()
        waste.stop.set()
        paper.stop.set()
        camera.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        raise SystemExit('Error: '+str(exc))
