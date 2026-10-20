"""Zoom digital de inspección; la geometría de vigilancia permanece original."""
import threading
import cv2
import numpy as np


class InspectionZoom:
    def __init__(self, level=1., enhancer=None):
        self.enhancer = enhancer
        self.lock = threading.Lock()
        self.level = float(np.clip(level, 1, 4))
        self.center = (.5, .5)
        self.display = None

    def set_level(self, value):
        with self.lock:
            self.level = float(np.clip(value, 1, 4))

    def adjust(self, delta):
        with self.lock:
            self.level = float(np.clip(self.level + delta, 1, 4))
        if self.level == 1 and self.enhancer is not None and self.enhancer.enabled:
            self.enhancer.toggle()

    def reset(self):
        with self.lock:
            self.level, self.center = 1., (.5, .5)
        if self.enhancer is not None and self.enhancer.enabled:
            self.enhancer.toggle()

    def region(self, shape):
        h, w = shape[:2]
        with self.lock:
            level, (cx, cy) = self.level, self.center
        if level <= 1:
            return None
        rw, rh = max(1, round(w / level)), max(1, round(h / level))
        x = int(np.clip(round(cx * w - rw / 2), 0, w - rw))
        y = int(np.clip(round(cy * h - rh / 2), 0, h - rh))
        return x, y, x + rw, y + rh

    def key(self, key):
        if key in (ord('+'), ord('=')):
            self.adjust(.25)
        elif key == ord('-'):
            self.adjust(-.25)
        elif key in (ord('i'),ord('I')) and self.enhancer is not None:
            self.enhancer.toggle()
            if self.enhancer.enabled and self.level < 2:
                self.set_level(2)
        elif key == ord('0'):
            self.reset()
        else:
            return False
        return True

    def mouse(self, event, x, y, flags, param):
        if event != cv2.EVENT_LBUTTONDOWN or self.display is None:
            return
        h, w, region, mini = self.display
        if h <= y < h + 40:
            if 8 <= x < 44: self.adjust(-.25)
            elif 50 <= x < 86: self.adjust(.25)
            elif 94 <= x < 222: self.reset()
            elif 232 <= x < 312: self.key(ord('i'))
            return
        if not (0 <= x < w and 0 <= y < h):
            return
        if mini is not None and mini[0] <= x < mini[2] and mini[1] <= y < mini[3]:
            mx, my, ex, ey = mini
            center = ((x - mx) / (ex - mx), (y - my) / (ey - my))
        else:
            x1, y1, x2, y2 = region
            center = ((x1 + x * (x2 - x1) / w) / w,
                      (y1 + y * (y2 - y1) / h) / h)
        with self.lock:
            self.center = center

    def render(self, image):
        h, w = image.shape[:2]
        region = self.region(image.shape)
        mini = None
        if region is None:
            view = image.copy()
            region = (0, 0, w, h)
        else:
            x1, y1, x2, y2 = region
            crop = image[y1:y2, x1:x2]
            if self.enhancer is not None and self.enhancer.enabled:
                crop = self.enhancer.enhance(crop)
            view = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
            mw = min(140, w // 4)
            mh = round(mw * h / w)
            mx, my = w - mw - 8, 8
            overview = cv2.resize(image, (mw, mh), interpolation=cv2.INTER_AREA)
            cv2.rectangle(overview, (round(x1 * mw / w), round(y1 * mh / h)),
                          (min(mw-1, round(x2 * mw / w)), min(mh-1, round(y2 * mh / h))), (0, 230, 255), 2)
            view[my:my+mh, mx:mx+mw] = overview
            cv2.rectangle(view, (mx-1, my-1), (mx+mw, my+mh), (255,255,255), 1)
            mini = (mx, my, mx+mw, my+mh)
        self.display = (h, w, region, mini)
        bar = np.full((40, w, 3), 32, np.uint8)
        buttons = [(8,44,'-'), (50,86,'+'), (94,222,'Vista completa')]
        if self.enhancer is not None:
            buttons.append((232,312,'IA: SI' if self.enhancer.enabled else 'IA: NO'))
        for left, right, label in buttons:
            cv2.rectangle(bar, (left,5), (right,34), (80,80,80), -1)
            cv2.putText(bar, label, (left+8,25), cv2.FONT_HERSHEY_SIMPLEX, .43, (255,255,255), 1, cv2.LINE_AA)
        level = w / (region[2] - region[0])
        cv2.putText(bar, f'{level:.2f}x | Clic: centrar | 0: volver', (322,25),
                    cv2.FONT_HERSHEY_SIMPLEX, .40, (230,230,230), 1, cv2.LINE_AA)
        return np.vstack([view, bar])


def restore_crop(items, region, shape):
    """Remapea resultados del zoom y descarta objetos cortados por su borde."""
    x1, y1, x2, y2 = region
    h, w = shape[:2]
    result = []
    for box, name, confidence in items:
        a, b, c, d = np.asarray(box, float)
        if ((x1 > 0 and a < 3) or (y1 > 0 and b < 3) or
            (x2 < w and c > x2-x1-3) or (y2 < h and d > y2-y1-3)):
            continue
        result.append((np.array([a+x1,b+y1,c+x1,d+y1]), name, confidence))
    return result
