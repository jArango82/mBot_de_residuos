"""Hacia dónde mira el robot, visto en la imagen y sin moverlo: la dirección de sus orugas.

Las orugas son dos franjas oscuras paralelas a los lados del robot. Se gira la máscara de lo oscuro de la caja del
robot y se suma a lo largo de cada dirección: en la de las orugas el perfil tiene los picos más marcados (varianza
máxima). Entre esa dirección y su perpendicular (el robot es casi cuadrado), se prefiere la que muestra dos picos
separados por un valle (dos orugas con el cuerpo, más claro, en medio).

Da el eje sin saber cuál es el frente (0-180°); la navegación elige el sentido con lo que ya sabe. En las grabaciones
del 2/11 (88 tramos en línea recta, comparando con hacia dónde se movió el robot): error mediano 5°, 81 % a menos
de 15° y 10 % de errores grandes (casi siempre la perpendicular), que la navegación descarta porque no cuadran con
el giro hecho. Antes el rumbo salía de pasos cortos de prueba, con ~20° de error.
"""
import math

import cv2
import numpy as np


def two_tracks(profile):
    """Picos en los tercios exteriores del tramo ocupado frente a la media del tercio central (0-1)."""
    on = np.nonzero(profile > .15 * profile.max())[0]
    if len(on) < 9:
        return 0.
    seg = profile[on[0]:on[-1] + 1]
    third = len(seg) // 3
    left, middle, right = seg[:third].max(), seg[third:-third].mean(), seg[-third:].max()
    return float((min(left, right) - middle) / max(seg.max(), 1e-6))


def track_axis(frame, box, margin=.08, step=3):
    """Ángulo de las orugas en la imagen (grados, 0-180, como atan2 con y hacia abajo) o None."""
    x, y, w, h = (int(round(v)) for v in box)
    m = int(margin * max(w, h))
    crop = frame[max(0, y - m):y + h + m, max(0, x - m):x + w + m]
    if crop.size == 0 or min(crop.shape[:2]) < 20:
        return None
    value = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[..., 2].astype(np.float32)
    dark = (value < .4 * np.percentile(value, 80)).astype(np.float32)
    if dark.mean() < .05:
        return None
    size = int(np.ceil(np.hypot(*dark.shape)))
    pad = np.zeros((size, size), np.float32)
    oy, ox = (size - dark.shape[0]) // 2, (size - dark.shape[1]) // 2
    pad[oy:oy + dark.shape[0], ox:ox + dark.shape[1]] = dark
    middle = (size / 2, size / 2)
    profiles = {angle: cv2.warpAffine(pad, cv2.getRotationMatrix2D(middle, angle, 1), (size, size)).sum(axis=1)
                for angle in range(0, 180, step)}
    variance = {angle: float(p.var()) for angle, p in profiles.items()}
    best = max(variance, key=variance.get)
    other = min(profiles, key=lambda a: abs((a - best - 90 + 90) % 180 - 90))
    if two_tracks(profiles[other]) > two_tracks(profiles[best]) + .1:
        best = other
    return float(best % 180)


def plane_axis(angle, box, plane):
    """El ángulo de la imagen llevado al plano del recuadro (grados, 0-180), alrededor del centro del robot."""
    x, y, w, h = box
    center = np.array([x + w / 2, y + h / 2], float)
    d = 10 * np.array([math.cos(math.radians(angle)), math.sin(math.radians(angle))])
    a, b = plane([center - d, center + d])
    return math.degrees(math.atan2(b[1] - a[1], b[0] - a[0])) % 180
