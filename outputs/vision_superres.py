"""FSRCNN x2 local para la vista; nunca se usa para clasificar ni contar."""
from pathlib import Path
import hashlib
import time
import cv2

MODEL = Path(__file__).resolve().parent/'models/superres/FSRCNN_x2.pb'
MODEL_SHA = '366b33f0084c7b3f2bf6724f0a2c77bca94fcec9d7b6d72389d330073b380d5c'
MODEL_URL = ('https://raw.githubusercontent.com/Saafke/FSRCNN_Tensorflow/'
             '6a4812c4ef1c4f5947d79beafa32a05a6eb4a94d/models/FSRCNN_x2.pb')


class SuperResolution:
    def __init__(self, enabled=False, model_path=MODEL):
        self.enabled = enabled
        self.path = Path(model_path)
        self.model = None
        self.status = 'IA desactivada | I: activar'
        self.elapsed_ms = 0.

    def toggle(self):
        self.enabled = not self.enabled
        self.status = 'IA activada: preparando vista' if self.enabled else 'IA desactivada | I: activar'

    def enhance(self, crop):
        if not self.enabled:
            return crop
        try:
            if self.model is None:
                if not self.path.is_file():
                    raise RuntimeError('Falta modelo: ejecutar preparar_modelos.py --solo-superres')
                if hashlib.sha256(self.path.read_bytes()).hexdigest() != MODEL_SHA:
                    raise RuntimeError('Modelo IA sin verificar: vuelve a descargarlo')
                self.model = cv2.dnn_superres.DnnSuperResImpl_create()
                self.model.readModel(str(self.path))
                self.model.setModel('fsrcnn', 2)
            start = time.monotonic()
            result = self.model.upsample(crop)
            self.elapsed_ms = (time.monotonic() - start) * 1000
            # Ante CPU saturada se recupera la vista original para mantener la respuesta.
            if self.elapsed_ms > 150:
                self.enabled = False
                self.status = 'IA pausada por lentitud | I: reintentar'
                return crop
            self.status = f'IA x2: solo vista | {self.elapsed_ms:.0f} ms | I: comparar con original'
            return result
        except Exception as exc:
            self.enabled = False
            self.model = None
            self.status = 'IA no disponible: ' + str(exc)
            return crop
