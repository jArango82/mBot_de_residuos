"""Geometría y decisiones de protección, sin conexión al robot."""
from dataclasses import dataclass
from itertools import combinations
import cv2
import numpy as np


def ordered_quad(points):
    p = np.asarray(points, np.float32).reshape(4, 2)
    center = p.mean(axis=0)
    p = p[np.argsort(np.arctan2(p[:, 1] - center[1], p[:, 0] - center[0]))]
    return np.roll(p, -int(np.argmin(p.sum(axis=1))), axis=0)


def black_lines(frame, contrast_min=30):
    """Segmentos de cinta oscura; no infiere un recinto ni habilita movimiento."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    light = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((41, 41), np.uint8))
    contrast = cv2.subtract(light, gray)
    mask = np.uint8((contrast >= contrast_min) & (gray < 180)) * 255
    raw = cv2.HoughLinesP(mask, 1, np.pi / 180, 60,
                         minLineLength=max(100, min(gray.shape) * .30), maxLineGap=12)
    if raw is None:
        return []
    height, width = gray.shape
    found = []
    for segment in sorted(raw.reshape(-1, 4),
                          key=lambda s: np.linalg.norm(s[2:] - s[:2]), reverse=True):
        a, b = segment[:2].astype(float), segment[2:].astype(float)
        direction = (b - a) / np.linalg.norm(b - a)
        normal = np.array([-direction[1], direction[0]])
        samples = np.linspace(a, b, 120)
        stripe = np.rint(samples[:, None, :] + np.arange(-3, 4)[None, :, None] * normal).astype(int)
        x = np.clip(stripe[:, :, 0], 0, width - 1)
        y = np.clip(stripe[:, :, 1], 0, height - 1)
        values = contrast[y, x].copy()
        values[gray[y, x] >= 180] = 0
        support = values.max(axis=1) >= contrast_min
        if support.mean() < .90:
            continue
        # Evita dibujar muchas líneas superpuestas sobre una misma cinta.
        duplicate = False
        for previous in found:
            c, d = previous[:2].astype(float), previous[2:].astype(float)
            old_direction = (d - c) / np.linalg.norm(d - c)
            if abs(direction @ old_direction) > .99 and max(abs((c-a) @ normal), abs((d-a) @ normal)) < 24:
                duplicate = True
                break
        if not duplicate:
            found.append(segment.copy())
        if len(found) >= 10:
            break
    return found


def _closed_enclosures(frame, threshold=70):
    """Busca el hueco interior de un contorno negro cerrado y cuadrilateral."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = cv2.inRange(gray, 0, threshold)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, hierarchy = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    height, width = gray.shape
    found = []
    for i, contour in enumerate(contours):
        # Un hueco blanco está a profundidad impar en la jerarquía.
        depth, parent = 0, hierarchy[0][i][3]
        while parent >= 0:
            depth += 1
            parent = hierarchy[0][parent][3]
        if depth % 2 != 1:
            continue
        area = cv2.contourArea(contour)
        if not width * height * .10 < area < width * height * .95:
            continue
        perimeter = cv2.arcLength(contour, True)
        poly = cv2.approxPolyDP(contour, .018 * perimeter, True)
        if len(poly) != 4 or not cv2.isContourConvex(poly):
            continue
        quad = ordered_quad(poly)
        if np.any(quad[:, 0] < 4) or np.any(quad[:, 0] > width - 5):
            continue
        if np.any(quad[:, 1] < 4) or np.any(quad[:, 1] > height - 5):
            continue
        if min(np.linalg.norm(np.roll(quad, -1, axis=0) - quad, axis=1)) < 65:
            continue
        found.append(quad)
    return sorted(found, key=cv2.contourArea, reverse=True)


def _intersection(a, b):
    point = np.cross(a, b)
    if abs(point[2]) < 1e-5:
        return None
    return point[:2] / point[2]


def _line_enclosures(frame, threshold):
    """Cuatro lados apoyados en cinta oscura, sin exigir píxeles conectados."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    local_light = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((19,19), np.uint8))
    contrast = cv2.subtract(local_light, gray)
    ceiling = min(235, max(180, threshold + 100))
    ink = np.uint8((contrast >= 18) & (gray < ceiling)) * 255
    raw = cv2.HoughLinesP(ink, 1, np.pi/180, 65,
                         minLineLength=max(70, min(height,width)*.19), maxLineGap=15)
    if raw is None:
        return []
    lines = []
    for segment in sorted(raw.reshape(-1,4),
                          key=lambda s: np.linalg.norm(s[2:]-s[:2]), reverse=True):
        start, end = segment[:2].astype(float), segment[2:].astype(float)
        direction = (end-start)/np.linalg.norm(end-start)
        normal = np.array([-direction[1], direction[0]])
        line = np.r_[normal, -normal@start]
        mid = (start+end)/2
        if any(abs(np.dot(line[:2], previous[:2])) > .994 and
               abs(np.dot(previous[:2], mid)+previous[2]) < 8 for previous in lines):
            continue
        lines.append(line)
        if len(lines) == 20:
            break
    opposite = [(i,j) for i,j in combinations(range(len(lines)),2)
                if abs(np.dot(lines[i][:2],lines[j][:2])) > .86]
    found = []
    for pair_a, pair_b in combinations(opposite,2):
        if len(set(pair_a+pair_b)) != 4:
            continue
        if abs(np.dot(lines[pair_a[0]][:2],lines[pair_b[0]][:2])) > .70:
            continue
        pts = [_intersection(lines[i],lines[j]) for i in pair_a for j in pair_b]
        if any(p is None for p in pts):
            continue
        quad = ordered_quad(pts)
        if (np.any(quad[:,0] < 4) or np.any(quad[:,0] > width-5) or
            np.any(quad[:,1] < 4) or np.any(quad[:,1] > height-5)):
            continue
        if not cv2.isContourConvex(quad):
            continue
        area = cv2.contourArea(quad)
        if not width*height*.10 < area < width*height*.95:
            continue
        lengths = np.linalg.norm(np.roll(quad,-1,axis=0)-quad,axis=1)
        if min(lengths) < 65:
            continue
        strengths = []
        for a,b in zip(quad,np.roll(quad,-1,axis=0)):
            direction = (b-a)/np.linalg.norm(b-a)
            normal = np.array([-direction[1],direction[0]])
            samples = np.linspace(a,b,180)
            stripe = np.rint(samples[:,None,:]+np.arange(-4,5)[None,:,None]*normal).astype(int)
            stripe[:,:,0] = np.clip(stripe[:,:,0],0,width-1)
            stripe[:,:,1] = np.clip(stripe[:,:,1],0,height-1)
            values = contrast[stripe[:,:,1],stripe[:,:,0]].astype(float)
            values[gray[stripe[:,:,1],stripe[:,:,0]] >= ceiling] = 0
            best = values.max(axis=1)
            support = best >= 18
            # No inventar un lado oculto: solo tolerar pequeñas interrupciones.
            longest_gap = run = 0
            for present in support:
                run = 0 if present else run+1
                longest_gap = max(run,longest_gap)
            if support.mean() < .88 or longest_gap > 11 or np.percentile(best,25) < 25:
                break
            strengths.append(float(np.median(best)))
        if len(strengths) != 4:
            continue
        # Entrar 6 px desde las líneas de cinta: el área válida queda dentro.
        center = quad.mean(axis=0)
        inset_lines = []
        for a,b in zip(quad,np.roll(quad,-1,axis=0)):
            direction=(b-a)/np.linalg.norm(b-a)
            n=np.array([-direction[1],direction[0]])
            if np.dot(n,center-a)<0:
                n=-n
            inset_lines.append(np.r_[n,-np.dot(n,a)-6])
        inner=ordered_quad([_intersection(inset_lines[i-1],inset_lines[i]) for i in range(4)])
        score = area * min(strengths)
        found.append((score,inner))
    found.sort(key=lambda item:item[0],reverse=True)
    distinct=[]
    for _,quad in found:
        if not any(np.max(np.linalg.norm(quad-q,axis=1)) < 15 for q in distinct):
            distinct.append(quad)
    return distinct


def black_enclosures(frame, threshold=70):
    """Prioriza cinta con cuatro lados; admite iluminación desigual y juntas cortas."""
    candidates = _line_enclosures(frame, threshold)
    for quad in _closed_enclosures(frame, threshold):
        if not any(np.max(np.linalg.norm(quad-q,axis=1)) < 15 for q in candidates):
            candidates.append(quad)
    return candidates


def same_boundary(reference, candidates, tolerance=10):
    return next((p for p in candidates
                 if np.max(np.linalg.norm(p - reference, axis=1)) <= tolerance), None)


@dataclass
class Pose:
    center: np.ndarray
    corners: np.ndarray
    side: float


def marker_pose(frame, detector, marker_id=7):
    corners, ids, _ = detector.detectMarkers(frame)
    if ids is None:
        return None
    selected = [c.reshape(4, 2) for c, i in zip(corners, ids.ravel()) if i == marker_id]
    if len(selected) != 1:
        return None
    p = selected[0]
    sides = np.linalg.norm(np.roll(p, -1, axis=0) - p, axis=1)
    if min(sides) < 12 or max(sides) / min(sides) > 1.6:
        return None
    # La menor dimensión evita subestimar el cuerpo cuando cambia el ángulo.
    return Pose(p.mean(axis=0), p, float(min(sides)))


def calibrate_body(pose, rect):
    x, y, w, h = rect
    if w < 20 or h < 20:
        raise ValueError('Selecciona el chasis completo, incluidas las orugas.')
    if not (x <= pose.center[0] <= x+w and y <= pose.center[1] <= y+h):
        raise ValueError('La etiqueta debe quedar dentro de la seleccion del robot.')
    box = np.float32([[x, y], [x+w, y], [x+w, y+h], [x, y+h]])
    radius = float(np.max(np.linalg.norm(box - pose.center, axis=1))) * 1.15
    return radius / pose.side


@dataclass
class Decision:
    safe: bool
    reason: str
    clearance: float | None = None
    required: float | None = None


def assess(boundary, pose, body_ratio, frame_age, speed=100, margin=20,
           measured_speed=0, prediction=None):
    """Todo el cuerpo + margen + recorrido posible hasta parada del firmware."""
    if frame_age > .30:
        return Decision(False, 'Imagen atrasada o camara perdida')
    if boundary is None:
        return Decision(False, 'Recuadro perdido o sin confirmar')
    if pose is None:
        return Decision(False, 'Robot no identificado')
    if body_ratio is None:
        return Decision(False, 'Falta seleccionar el cuerpo del robot (R)')
    center = tuple(float(x) for x in pose.center)
    clearance = cv2.pointPolygonTest(boundary, center, True)
    radius = body_ratio * pose.side
    # 600 ms firmware + 300 ms frescura + 350 ms transporte/frenado estimado.
    # Son reservas de diseño; hay que validar velocidad y frenado físicos.
    required = radius + margin + max(speed, measured_speed) * (1.25 + frame_age)
    if clearance <= required:
        return Decision(False, 'Limite: detener y activar alarma', clearance, required)
    if prediction is not None:
        future = cv2.pointPolygonTest(boundary, tuple(float(x) for x in prediction), True)
        if future <= radius + margin:
            return Decision(False, 'Trayectoria hacia el limite', clearance, required)
    return Decision(True, 'Zona segura', clearance, required)
