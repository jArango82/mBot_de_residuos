"""Hojas de color dentro del recuadro donde se llevan los residuos: amarilla para los aprovechables (cartón, latas,
botellas) y roja para los peligrosos (envase de blanqueador).

Se buscan por color en la imagen de análisis: grandes, planas y de color saturado. La hoja roja es más clara que
el suelo (papel) y la caja roja, más oscura (cartón con sombra): así no se confunden aunque tengan el mismo tono.
Como no se mueven, se guardan en coordenadas del recuadro (como la navegación y el conteo) y se recuerdan aunque
el robot o un residuo las tape en parte.
"""
import cv2
import numpy as np

SIZE = 400.
SQUARE = np.float32([[0, 0], [SIZE, 0], [SIZE, SIZE], [0, SIZE]])
# Qué residuo va a cada hoja (1/11): la amarilla para los aprovechables y la roja para los peligrosos.
DESTINO = {'caja de carton': 'amarilla', 'lata': 'amarilla', 'botella de vidrio': 'amarilla',
           'botella de plastico': 'amarilla', 'envase de blanqueador': 'roja'}
GRUPO = {'amarilla': 'aprovechables', 'roja': 'peligrosos'}
COLORES = {'roja': (40, 40, 230), 'amarilla': (0, 220, 255)}


def masks(frame, polygon):
    """Máscaras de papel rojo y amarillo dentro del recuadro (con un margen)."""
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    zone = np.zeros((h, w), np.uint8)
    cv2.fillConvexPoly(zone, np.int32(np.round(polygon)), 1)
    zone = cv2.dilate(zone, np.ones((21, 21), np.uint8)) > 0
    plain = zone & (sat < 40)
    floor = float(np.median(val[plain])) if plain.sum() > 200 else 160.
    red = zone & ((hue <= 10) | (hue >= 170)) & (sat >= 90) & (val >= .9 * floor)
    yellow = zone & (hue >= 15) & (hue <= 40) & (sat >= 90) & (val >= .45 * floor)
    kernel = np.ones((3, 3), np.uint8)
    found = {name: cv2.morphologyEx(cv2.morphologyEx(np.uint8(m) * 255, cv2.MORPH_OPEN, kernel), cv2.MORPH_CLOSE, kernel)
             for name, m in (('roja', red), ('amarilla', yellow))}
    # Suelo: poco color y brillo parecido al del suelo (para recortar detecciones, no para buscar hojas).
    found['suelo'] = np.uint8((sat < 45) & (np.abs(val - floor) < 30)) * 255
    return found


def find_sheets(frame, polygon, min_area=120):
    """{color: cuadrilátero (4 x 2, imagen)} de la hoja de cada color más grande y rectangular que se vea."""
    found = {}
    found_masks = masks(frame, polygon)
    for name in COLORES:
        mask = found_masks[name]
        count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
        best = None
        # Primero trozos sueltos; los grupos de trozos solo si no hay ninguna hoja entera (si no, la caja roja
        # junto a la hoja la agrandaba).
        for groups in ([[k] for k in range(1, count)], pieces(stats, count)):
            for group in groups:
                area = int(stats[group, cv2.CC_STAT_AREA].sum())
                if area < min_area:
                    continue
                points = np.column_stack(np.nonzero(labels == group[0] if len(group) == 1 else np.isin(labels, group))[::-1]).astype(np.float32)
                rect = cv2.minAreaRect(points)
                fill = area / max(rect[1][0] * rect[1][1], 1)
                if min(rect[1]) < 6:
                    continue
                if len(group) == 1:
                    # Una hoja es un rectángulo lleno; manchas alargadas o huecas (reflejos, cables) no.
                    if fill < .6:
                        continue
                elif not covered_sheet(points, rect, area, found_masks['suelo']):
                    continue
                if best is None or area > best[0]:
                    best = (area, cv2.boxPoints(rect))
            if best is not None:
                found[name] = best[1]
                break
    return found


def pieces(stats, count, reach=25):
    """Trozos de color a menos de reach px unos de otros: un residuo tumbado encima parte la hoja en dos o tres
    (1/11: el blanqueador en diagonal sobre la hoja roja dejaba dos triángulos de relleno 0,5 y la hoja no se
    encontraba). Grupos de dos o más trozos de al menos 15 px."""
    parts = [k for k in range(1, count) if stats[k, cv2.CC_STAT_AREA] >= 15]
    group = {k: k for k in parts}

    def root(k):
        while group[k] != k:
            k = group[k]
        return k
    for i, a in enumerate(parts):
        ax, ay, aw, ah = stats[a, :4]
        for b in parts[i + 1:]:
            bx, by, bw, bh = stats[b, :4]
            if max(bx - (ax + aw), ax - (bx + bw)) <= reach and max(by - (ay + ah), ay - (by + bh)) <= reach:
                group[root(b)] = root(a)
    together = {}
    for k in parts:
        together.setdefault(root(k), []).append(k)
    return [g for g in together.values() if len(g) > 1]


def covered_sheet(points, rect, area, floor):
    """Trozos que son una hoja con algo encima: juntos casi forman un rectángulo (su envolvente llena ≥ 75 %), el
    color cubre al menos el 35 % y lo que falta no es suelo (≤ 20 %: es el residuo encima). Dos manchas separadas
    por suelo, no. (Blanqueador en diagonal sobre la hoja roja con poca luz: envolvente 0,81, color 0,40, suelo 0,11.)"""
    hull = cv2.convexHull(points)
    rect_area = max(rect[1][0] * rect[1][1], 1)
    hull_area = cv2.contourArea(hull)
    if hull_area < .75 * rect_area or area < .35 * rect_area:
        return False
    inside = np.zeros(floor.shape, np.uint8)
    cv2.fillConvexPoly(inside, np.int32(np.round(hull.reshape(-1, 2))), 1)
    return (floor[inside > 0] > 0).mean() <= .2


class Sheets:
    """Hojas confirmadas, en coordenadas del recuadro. Una hoja se confirma vista en el mismo sitio en ≥ 5 imágenes
    durante ≥ 1 s; después se recuerda (no se mueven) y solo se actualiza cuando se ve entera."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.known = {}        # color -> cuadrilátero en el plano
        self.pending = {}      # color -> [(instante, cuadrilátero en el plano)]

    @staticmethod
    def matrix(polygon):
        return cv2.getPerspectiveTransform(np.float32(polygon), SQUARE)

    def update(self, frame, polygon, now):
        matrix = self.matrix(polygon)
        for name, quad in find_sheets(frame, polygon).items():
            plane = cv2.perspectiveTransform(np.float32(quad).reshape(-1, 1, 2), matrix).reshape(-1, 2)
            area = cv2.contourArea(plane)
            if name in self.known:
                old = self.known[name]
                # Vista entera y casi en el mismo sitio: se afina despacio. Tapada en parte: se conserva.
                if area > .8 * cv2.contourArea(old) and np.linalg.norm(plane.mean(0) - old.mean(0)) < 30:
                    self.known[name] = .9 * old + .1 * self.align(old, plane)
                continue
            history = [(t, q) for t, q in self.pending.get(name, []) if now - t < 3 and
                       np.linalg.norm(q.mean(0) - plane.mean(0)) < 20]
            history.append((now, plane))
            self.pending[name] = history
            if len(history) >= 5 and now - history[0][0] >= 1:
                self.known[name] = np.median([self.align(history[-1][1], q) for _, q in history], axis=0).astype(np.float32)
        return self.known

    @staticmethod
    def align(reference, quad):
        return min((np.roll(quad, k, axis=0) for k in range(4)), key=lambda q: np.abs(q - reference).sum())

    def in_image(self, polygon):
        """Hojas conocidas llevadas a la imagen actual (para dibujarlas y para filtrar detecciones)."""
        back = np.linalg.inv(self.matrix(polygon))
        return {name: cv2.perspectiveTransform(np.float32(q).reshape(-1, 1, 2), back).reshape(-1, 2)
                for name, q in self.known.items()}


def on_sheet(box, sheets_image, frame, polygon=None, paper=None):
    """None si la detección es solo una hoja (el detector llamaba «caja» a la hoja roja); si no, la misma caja.

    Es la hoja sola si la detección coincide con ella y dentro de la hoja no hay nada más oscuro que el papel. Con
    poca luz la caja roja tiene casi el mismo color que la hoja, pero sus caras laterales siempre son más oscuras
    (V 60-90 frente a 150-180 del papel): se compara con el brillo de la propia hoja en esa imagen, no con un
    umbral fijo. (polygon y paper se aceptan por compatibilidad.)"""
    x1, y1, x2, y2 = (float(v) for v in box)
    H, W = frame.shape[:2]
    for name, quad in sheets_image.items():
        sx1, sy1 = quad.min(axis=0); sx2, sy2 = quad.max(axis=0)
        w = max(0., min(x2, sx2) - max(x1, sx1)); h = max(0., min(y2, sy2) - max(y1, sy1))
        union = (x2 - x1) * (y2 - y1) + (sx2 - sx1) * (sy2 - sy1) - w * h
        if union <= 0 or w * h / union < .5:
            continue
        inside = np.zeros((H, W), np.uint8)
        cv2.fillConvexPoly(inside, np.int32(np.round(quad)), 1)
        inside = cv2.erode(inside, np.ones((3, 3), np.uint8)) > 0
        if inside.sum() < 30:
            continue
        val = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)[..., 2][inside].astype(float)
        dark = (val < .8 * np.median(val)).mean()
        if dark < .1:
            return None
    return list(box)


# Un residuo está «en su hoja» si su centro cae encima o si al menos el 40 % de su caja la pisa (2/11: el blanqueador,
# largo, quedaba con el cuerpo sobre la hoja roja y el centro justo fuera; el robot volvía a por él, daba vueltas junto
# a la cinta y no se contaba).
ON_SHEET = .4


def share_on(quad, sheet):
    """Parte (0-1) del cuadrilátero quad que cae sobre la hoja (los dos convexos y en las mismas coordenadas)."""
    quad, sheet = np.float32(quad).reshape(-1, 2), np.float32(sheet).reshape(-1, 2)
    area = cv2.contourArea(quad)
    if area <= 0:
        return 0.
    inter, _ = cv2.intersectConvexConvex(quad, sheet)
    return float(inter / area)


def is_sheet(box, sheets_image, frame):
    return on_sheet(box, sheets_image, frame) is None


def area_of(box):
    return max(float(box[2]) - float(box[0]), 0.) * max(float(box[3]) - float(box[1]), 0.)


def inside_of(small, big):
    """Fracción de la caja small que cae dentro de big."""
    w = max(0., min(small[2], big[2]) - max(small[0], big[0])); h = max(0., min(small[3], big[3]) - max(small[1], big[1]))
    return w * h / max(area_of(small), 1e-6)
