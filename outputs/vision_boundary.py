"""Selección automática y estabilidad temporal del recuadro de cinta."""
import numpy as np
import cv2


def tape_image(frame):
    """Compensa poca luz solo para detectar cinta; no modifica la imagen del robot."""
    gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
    light=float(np.percentile(gray[::4,::4],95))
    gain=min(2.5,max(1.,100/max(light,1)))
    return cv2.convertScaleAbs(frame,alpha=gain) if gain > 1.05 else frame


class AutoBoundary:
    tolerance = 20

    def __init__(self):
        self.reset()

    def reset(self):
        self.boundary = None
        self.visible = False
        self.pending = []
        self.last_stamp = None
        self.last_seen = -float('inf')

    @staticmethod
    def align(reference, quad):
        return min((np.roll(quad,k,axis=0) for k in range(4)),
                   key=lambda q:np.max(np.linalg.norm(q-reference,axis=1)))

    def confirm(self, quad, stamp):
        self.boundary = np.asarray(quad,np.float32).copy()
        self.visible = True
        self.last_seen = stamp
        self.pending = []

    def supported(self, lines):
        for a,b in zip(self.boundary,np.roll(self.boundary,-1,axis=0)):
            axis=(b-a)/np.linalg.norm(b-a)
            normal=np.array([-axis[1],axis[0]])
            length=np.linalg.norm(b-a)
            for line in lines:
                points=np.asarray(line,float).reshape(2,2)-a
                projections=points@axis
                overlap=min(length,projections.max())-max(0,projections.min())
                if np.max(np.abs(points@normal)) <= self.tolerance and overlap >= .60*length:
                    break
            else:
                return False
        return True

    def update(self, quads, lines, stamp, now):
        """Devuelve True al seleccionar/reubicar; nunca habilita motores."""
        if now-stamp > .30:
            self.visible=False
            self.pending=[]
            return False
        if stamp == self.last_stamp:
            return False
        self.last_stamp=stamp
        self.visible=False
        if self.boundary is not None:
            aligned=[self.align(self.boundary,q) for q in quads]
            near=[q for q in aligned if np.max(np.linalg.norm(q-self.boundary,axis=1)) <= self.tolerance]
            if near:
                nearest=min(near,key=lambda q:np.max(np.linalg.norm(q-self.boundary,axis=1)))
                self.boundary=.65*self.boundary+.35*nearest
                self.visible=True
            elif self.supported(lines):
                # Cada lado sigue respaldado por cinta actual, aunque falle el contorno.
                self.visible=True
            if self.visible:
                self.last_seen=stamp
                self.pending=[]
                return False
            if stamp-self.last_seen < .8:
                return False
        # Exige varias imágenes diferentes, durante al menos 0.4 s.
        if not quads:
            if self.pending and stamp-self.pending[-1][0] > .2:
                self.pending=[]
            return False
        candidate=quads[0]
        if self.pending:
            choices=[self.align(self.pending[0][1],q) for q in quads]
            candidate=min(choices,key=lambda q:np.max(np.linalg.norm(q-self.pending[0][1],axis=1)))
            if stamp-self.pending[-1][0] > .2 or np.max(np.linalg.norm(candidate-self.pending[0][1],axis=1)) > self.tolerance:
                self.pending=[]
        self.pending.append((stamp,np.asarray(candidate,np.float32).copy()))
        if len(self.pending) >= 6 and stamp-self.pending[0][0] >= .4:
            self.confirm(np.median([q for _,q in self.pending],axis=0),stamp)
            return True
        return False
