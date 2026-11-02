"""Recuadro de cinta negra pensado para condiciones malas: poca luz o luz desigual, reflejos, sombras, gente o
zapatos tapando parte de la cinta, perspectiva fuerte (cámara baja) y cámara en la mano.

La cinta se reconoce por ser una franja más oscura que el suelo que tiene a los DOS lados, en proporción y no
en valor absoluto: así sirve igual con el suelo iluminado que en penumbra. El borde de una sombra o de un
objeto oscuro solo tiene suelo claro a un lado y no cuenta como cinta.
"""
from itertools import combinations
import warnings
import cv2
import numpy as np

INK = .3        # la cinta es al menos un 30 % más oscura que el suelo de al lado
FAINT = .2      # el lado lejano, más fino y borroso por la perspectiva, puede quedarse en un 20 %
KERNEL = 21     # px a 640: más ancho que la cinta (3-10 px), para estimar el suelo sin ella
INSET = 6       # px: el recuadro devuelto queda por dentro de la cinta, como el detector anterior


def ink_map(frame):
    """Tinta relativa de cada píxel (0 = como el suelo de alrededor) y gris suavizado."""
    gray = cv2.GaussianBlur(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).astype(np.float32), (0, 0), 1.2)
    light = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, np.ones((KERNEL, KERNEL), np.uint8))
    return (light - gray) / (light + 12), gray


def ordered(points):
    p = np.asarray(points, np.float32).reshape(4, 2)
    c = p.mean(axis=0)
    p = p[np.argsort(np.arctan2(p[:, 1] - c[1], p[:, 0] - c[0]))]
    return np.roll(p, -int(np.argmin(p.sum(axis=1))), axis=0)


def cross(a, b):
    p = np.cross(a, b)
    return None if abs(p[2]) < 1e-6 else p[:2] / p[2]


def offset(quad, distance):
    """Desplaza cada lado hacia dentro (distancia positiva) o hacia fuera (negativa)."""
    quad = np.asarray(quad, float)
    center = quad.mean(axis=0)
    moved = []
    for a, b in zip(quad, np.roll(quad, -1, axis=0)):
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        if n @ (center - a) < 0:
            n = -n
        moved.append(np.r_[n, -n @ a - distance])
    return ordered([cross(moved[k - 1], moved[k]) for k in range(4)])


def _band(shape, a, b, offsets, samples=120):
    h, w = shape
    d = (b - a) / max(np.linalg.norm(b - a), 1e-6)
    n = np.array([-d[1], d[0]])
    pts = np.rint(np.linspace(a, b, samples)[:, None, :] + offsets[None, :, None] * n).astype(int)
    inside = (pts[..., 0] >= 0) & (pts[..., 0] < w) & (pts[..., 1] >= 0) & (pts[..., 1] < h)
    return np.clip(pts[..., 0], 0, w - 1), np.clip(pts[..., 1], 0, h - 1), inside


def _summary(ink, visible):
    # Los tramos fuera de la imagen no cuentan ni a favor ni en contra.
    if visible.mean() < .6:
        return 0., 0.
    present = ink[visible] >= INK
    return float(present.mean()), float(np.median(ink[visible][present])) if present.any() else 0.


def tape_support(gray, a, b, half=4, gap=3, reach=14):
    """Fracción del lado a-b con cinta (franja oscura con suelo claro a los dos lados) y tinta mediana."""
    offsets = np.arange(-half - reach, half + reach + 1)
    x, y, inside = _band(gray.shape, a, b, offsets)
    values = np.where(inside, gray[y, x], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)   # filas enteras fuera de la imagen
        center = np.nanmin(values[:, np.abs(offsets) <= half], axis=1)
        # Con la cinta pegada al borde de la imagen, un lado queda fuera: entonces se usa solo el visible (fmin).
        light = np.fmin(np.nanmax(values[:, offsets <= -half - gap], axis=1),
                        np.nanmax(values[:, offsets >= half + gap], axis=1))
    ink = (light - center) / (light + 12)
    visible = ~np.isnan(ink)
    return _summary(np.where(visible, ink, -1), visible)


def tape_lines(mask, limit=18):
    """Rectas candidatas (n, c con n·p + c = 0), las más largas y continuas primero."""
    h, w = mask.shape
    # Fuera manchas sueltas (vetas, textura): la cinta forma trazos largos aunque esté tapada a ratos.
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, bool)
    keep[1:] = np.maximum(stats[1:, 2], stats[1:, 3]) >= max(25, .07 * min(h, w))
    mask = np.uint8(keep[labels]) * 255
    raw = cv2.HoughLinesP(mask, 1, np.pi / 180, 40, minLineLength=max(40, .12 * min(h, w)), maxLineGap=15)
    if raw is None:
        return []
    near = cv2.dilate(mask, np.ones((5, 5), np.uint8)) > 0
    raw = raw.reshape(-1, 4).astype(float)
    s = np.rint(raw[:, None, :2] + np.linspace(0, 1, 60)[None, :, None] * (raw[:, None, 2:] - raw[:, None, :2])).astype(int)
    density = near[np.clip(s[..., 1], 0, h - 1), np.clip(s[..., 0], 0, w - 1)].mean(axis=1)
    # Una recta larga hecha de manchas separadas no es cinta.
    score = np.linalg.norm(raw[:, 2:] - raw[:, :2], axis=1) * density ** 2
    lines = []
    for k in np.argsort(-score):
        a, b = raw[k, :2], raw[k, 2:]
        d = (b - a) / np.linalg.norm(b - a)
        n = np.array([-d[1], d[0]])
        mid = (a + b) / 2
        if any(abs(n @ l[:2]) > .995 and abs(l[:2] @ mid + l[2]) < 10 for l in lines):
            continue
        lines.append(np.r_[n, -n @ a])
        if len(lines) == limit:
            break
    return lines


def _profiles(lines, ratio, gray, half=4, gap=3, reach=14, step=2, hidden=()):
    """Cinta a lo largo de cada recta, píxel a píxel, en sumas acumuladas: así el apoyo de cualquier tramo
    entre dos esquinas sale con dos restas, sin volver a muestrear la imagen para cada candidato."""
    h, w = gray.shape
    n = lines[:, :2]
    d = np.stack([n[:, 1], -n[:, 0]], axis=1)
    p0 = -lines[:, 2:3] * n
    # Solo el tramo de cada recta que cruza la imagen: t es la distancia a lo largo de la recta (p0·d = 0).
    edge = half + reach
    along = np.array([[0, 0], [w - 1, 0], [0, h - 1], [w - 1, h - 1]], float) @ d.T
    start = np.floor(along.min(axis=0)).astype(int) - edge
    # Una muestra cada `step` px a lo largo de la recta basta para medir qué parte tiene cinta.
    span = (int(np.ceil(np.ptp(along, axis=0).max())) + 2 * edge + 2) // step + 1
    t = (start[:, None] + step * np.arange(span)[None, :]).astype(float)
    offsets = np.arange(-edge, edge + 1)
    pts = np.rint(p0[:, None, None] + t[:, :, None, None] * d[:, None, None] +
                  offsets[None, None, :, None] * n[:, None, None]).astype(int)
    inside = (pts[..., 0] >= 0) & (pts[..., 0] < w) & (pts[..., 1] >= 0) & (pts[..., 1] < h)
    for x1, y1, x2, y2 in hidden:
        # Lo que tapa el robot no cuenta ni a favor ni en contra, como lo que queda fuera de la imagen.
        inside &= ~((pts[..., 0] >= x1) & (pts[..., 0] <= x2) & (pts[..., 1] >= y1) & (pts[..., 1] <= y2))
    x, y = np.clip(pts[..., 0], 0, w - 1), np.clip(pts[..., 1], 0, h - 1)
    core = np.abs(offsets) <= half
    quick_seen = inside[..., core].any(axis=2)
    darkest = np.where(inside[..., core], ratio[y[..., core], x[..., core]], -1).max(axis=2)
    values = np.where(inside, gray[y, x], np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', RuntimeWarning)   # tramos enteros fuera de la imagen
        center = np.nanmin(values[..., core], axis=2)
        # Con la cinta pegada al borde de la imagen, un lado queda fuera: entonces se usa solo el visible (fmin).
        light = np.fmin(np.nanmax(values[..., offsets <= -half - gap], axis=2),
                        np.nanmax(values[..., offsets >= half + gap], axis=2))
        ink = (light - center) / (light + 12)
    seen = ~np.isnan(ink)
    ink = np.nan_to_num(ink, nan=-1)
    ok = seen & (ink >= INK)

    def total(a):
        return np.concatenate([np.zeros((len(a), 1)), np.cumsum(a, axis=1)], axis=1)
    return {'p0': p0, 'd': d, 'start': start, 'span': span, 'step': step,
            'quick': (total(darkest >= INK), total(quick_seen)), 'quick_faint': (total(darkest >= FAINT), total(quick_seen)),
            'tape': (total(ok), total(seen), total(np.where(ok, ink, 0))), 'tape_faint': (total(seen & (ink >= FAINT)), total(seen))}


def _sides(profile, kind, line, a, b):
    """Apoyo (fracción con cinta de la parte visible) y tinta media de los tramos a-b sobre cada recta."""
    p0, d, start, span, step = (profile[k] for k in ('p0', 'd', 'start', 'span', 'step'))
    p0, d, start = p0[line], d[line], start[line]
    ta, tb = ((a - p0) * d).sum(axis=1), ((b - p0) * d).sum(axis=1)
    lo = np.clip(np.ceil((np.minimum(ta, tb) - start) / step).astype(int), 0, span - 1)
    hi = np.clip(np.floor((np.maximum(ta, tb) - start) / step).astype(int) + 1, 1, span)
    sums = [c[line, hi] - c[line, lo] for c in profile[kind]]
    ok, seen = sums[0], sums[1]
    # Los tramos fuera de la imagen no cuentan ni a favor ni en contra.
    support = np.where(seen >= .6 * np.maximum(hi - lo, 1), ok / np.maximum(seen, 1), 0.)
    strength = sums[2] / np.maximum(ok, 1) if len(sums) > 2 else None
    return support, strength


def tape_squares(frame, exclude=(), limit=6):
    """Recuadros de cinta, el más probable primero. Cada uno es el interior (INSET px dentro de la cinta).
    exclude: cajas [x1, y1, x2, y2] (el robot) donde no puede estar el centro de un recuadro pequeño."""
    h, w = frame.shape[:2]
    ratio, gray = ink_map(frame)
    mask = np.uint8(ratio >= INK) * 255
    lines = tape_lines(mask)
    # El lado lejano puede ser tan pálido que ni aparece como recta: se buscan rectas también con el umbral bajo.
    # Solo podrán ser el cuarto lado pálido (los otros tres tienen que ser claros, ver accepted).
    for extra in tape_lines(np.uint8(ratio >= FAINT) * 255, limit=12):
        if len(lines) >= 26:
            break
        if not any(abs(extra[:2] @ l[:2]) > .99 and abs(abs(extra[2]) - abs(l[2])) < 8 for l in lines):
            lines.append(extra)
    if len(lines) < 4:
        return []
    lines = np.array(lines)
    dots = np.abs(lines[:, :2] @ lines[:, :2].T)
    corners = np.cross(lines[:, None, :], lines[None, :, :])
    with np.errstate(divide='ignore', invalid='ignore'):
        corners = corners[..., :2] / corners[..., 2:]
    # Lados opuestos: hasta 65° entre sí por la perspectiva. Lo que los distingue de los contiguos es que cada
    # pareja es más paralela entre sí que con la otra.
    pairs = np.array([(i, j) for i, j in combinations(range(len(lines)), 2) if dots[i, j] > .42]).reshape(-1, 2)
    if len(pairs) < 2:
        return []
    # Todas las combinaciones de dos parejas a la vez.
    first, second = np.triu_indices(len(pairs), 1)
    A, B = pairs[first], pairs[second]
    between = np.max([dots[A[:, i], B[:, j]] for i in (0, 1) for j in (0, 1)], axis=0)
    keep = ((A[:, :, None] != B[:, None, :]).all(axis=(1, 2)) & (between <= .8) &
            (between < np.minimum(dots[A[:, 0], A[:, 1]], dots[B[:, 0], B[:, 1]])))
    A, B = A[keep], B[keep]
    # Esquinas en orden; el lado k va de la esquina k a la k+1 sobre la recta side_line[k].
    Q = np.stack([corners[A[:, 0], B[:, 0]], corners[A[:, 0], B[:, 1]],
                  corners[A[:, 1], B[:, 1]], corners[A[:, 1], B[:, 0]]], axis=1)
    side_line = np.stack([A[:, 0], B[:, 1], A[:, 1], B[:, 0]], axis=1)
    with np.errstate(invalid='ignore'):
        # La cinta puede quedar pegada al borde de la imagen, o un poco fuera en una esquina.
        keep = (np.isfinite(Q).all(axis=(1, 2)) & (Q >= -12).all(axis=(1, 2)) &
                (Q[:, :, 0] <= w + 12).all(axis=1) & (Q[:, :, 1] <= h + 12).all(axis=1))
    Q, side_line = Q[keep], side_line[keep]
    following = np.roll(Q, -1, axis=1)
    edges = following - Q
    turns = edges[:, :, 0] * np.roll(edges, -1, axis=1)[:, :, 1] - edges[:, :, 1] * np.roll(edges, -1, axis=1)[:, :, 0]
    areas = np.abs((Q[:, :, 0] * following[:, :, 1] - following[:, :, 0] * Q[:, :, 1]).sum(axis=1)) / 2
    lengths = np.linalg.norm(edges, axis=2)
    # Un cuadrado visto en perspectiva conserva esquinas razonables; un «recuadro» formado por el cuerpo del
    # robot y un cable suele ser casi un triángulo.
    with np.errstate(invalid='ignore', divide='ignore'):
        cosines = -(np.roll(edges, 1, axis=1) * edges).sum(axis=2) / (np.roll(lengths, 1, axis=1) * lengths)
    keep = (((turns > 0).all(axis=1) | (turns < 0).all(axis=1)) & (.08 * w * h < areas) & (areas < .97 * w * h) &
            (lengths.min(axis=1) >= 50) & (np.abs(cosines) <= np.cos(np.radians(40))).all(axis=1))
    Q, side_line, areas = Q[keep], side_line[keep], areas[keep]
    if not len(Q):
        return []
    # Solo se recorren las rectas que forman algún candidato.
    used = np.unique(side_line)
    profile = _profiles(lines[used], ratio, gray, hidden=exclude)
    # Se toleran tramos tapados (zapatos, una persona, el robot) si cada lado se ve en su mayor parte.
    a, b, line = Q.reshape(-1, 2), np.roll(Q, -1, axis=1).reshape(-1, 2), np.searchsorted(used, side_line.reshape(-1))
    quick = _sides(profile, 'quick', line, a, b)[0].reshape(-1, 4)
    quick_faint = _sides(profile, 'quick_faint', line, a, b)[0].reshape(-1, 4)
    tape, strength = (v.reshape(-1, 4) for v in _sides(profile, 'tape', line, a, b))
    tape_faint = _sides(profile, 'tape_faint', line, a, b)[0].reshape(-1, 4)

    def accepted(clear, faint):
        # Todos los lados claros; o tres muy claros y uno pálido (el lejano, fino y borroso por la perspectiva).
        normal = (clear.min(axis=1) >= .5) & (clear.mean(axis=1) >= .7)
        weak = np.argmin(clear, axis=1)
        rest = np.sort(clear, axis=1)[:, 1:]
        # Los otros tres, claros (todos ≥ 0,7 y de media ≥ 0,85: con el robot o una hoja junto a un lado, uno puede
        # quedarse en 0,79; con «todos ≥ 0,8» se perdía el recuadro de la 5.ª prueba).
        return normal | ((rest.min(axis=1) >= .7) & (rest.mean(axis=1) >= .85) & (faint[np.arange(len(faint)), weak] >= .6))
    keep = accepted(quick, quick_faint) & accepted(tape, tape_faint)
    support = np.where(tape >= .5, tape, .8 * tape_faint)
    scores = np.sqrt(areas) * support.mean(axis=1) * support.min(axis=1) * np.maximum(strength.min(axis=1), .1)
    distinct = []
    for k in np.flatnonzero(keep)[np.argsort(-scores[keep])]:
        quad = Q[k].astype(np.float32)
        center = quad.mean(axis=0)
        if any(e[0] <= center[0] <= e[2] and e[1] <= center[1] <= e[3] and areas[k] < 3 * (e[2] - e[0]) * (e[3] - e[1])
               for e in exclude):
            continue  # un «recuadro» sobre el propio robot
        inner = offset(quad, INSET)
        if any(np.max(np.linalg.norm(inner - d, axis=1)) < 15 for d in distinct):
            continue
        # Dentro debe haber sobre todo suelo, no la maraña de bordes oscuros del robot.
        inner_mask = np.zeros((h, w), np.uint8)
        cv2.fillConvexPoly(inner_mask, np.int32(quad), 1)
        cv2.polylines(inner_mask, [np.int32(quad)], True, 0, 14)
        if inner_mask.any() and float((mask[inner_mask == 1] > 0).mean()) > .12:
            continue
        distinct.append(inner)
        if len(distinct) == limit:
            break
    return distinct


def square_support(frame, inner, half=6):
    """Apoyo de cinta en cada lado de un recuadro ya conocido (interior), en la imagen actual."""
    _, gray = ink_map(frame)
    quad = offset(inner, -INSET)
    return np.array([tape_support(gray, a, b, half=half)[0] for a, b in zip(quad, np.roll(quad, -1, axis=0))])
