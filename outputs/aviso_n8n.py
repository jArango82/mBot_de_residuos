"""Manda cada residuo separado a n8n (un webhook) para que lo apunte como fila en una hoja de cálculo, y guarda lo
que n8n contesta («✅ Apuntado en Google Sheets: Lata → hoja amarilla» o el motivo si falló) para mostrarlo en el panel.

Se envía en un hilo aparte: el bucle del robot nunca espera a la red. Si n8n no está abierto o no responde, los
avisos se guardan en orden (hasta 500) y se reintentan cada pocos segundos; no se pierde ninguno mientras el
programa siga abierto. Solo se envían datos del conteo (hora, residuo, hoja, confianza, sesión), nunca imágenes.
"""
import json
import queue
from collections import deque
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from vision_hojas import DESTINO, GRUPO

DEFAULT_URL = 'http://localhost:5678/webhook/residuos'
NAME = {'caja de carton': 'Caja de cartón', 'lata': 'Lata', 'botella de vidrio': 'Botella de vidrio',
        'botella de plastico': 'Botella de plástico', 'envase de blanqueador': 'Envase de blanqueador'}


def payload(event, total):
    """Fila para la hoja de cálculo a partir de un evento del conteo."""
    label = event['category']
    sheet = DESTINO.get(label, '')
    moment = datetime.fromtimestamp(event['at'])
    return {'fecha': moment.strftime('%Y-%m-%d'), 'hora': moment.strftime('%H:%M:%S'),
            'residuo': NAME.get(label, label), 'clase': label, 'hoja': sheet, 'grupo': GRUPO.get(sheet, 'fuera del recuadro'),
            'confianza': round(float(event['confidence']), 2), 'sesion': event['session'][:8], 'total_sesion': total}


class N8nSender:
    def __init__(self, url=DEFAULT_URL, timeout=10., retry=5., limit=500):
        # timeout: n8n contesta después de escribir en Google Sheets (~1 s).
        self.url, self.timeout, self.retry = url, timeout, retry
        self.pending = queue.Queue(maxsize=limit)
        self.sent = 0
        self.replies = deque(maxlen=5)   # últimas respuestas de n8n: {'mensaje', 'at', 'ok'}
        self.status = f'n8n: esperando residuos ({url})'
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def send(self, event, total):
        try:
            self.pending.put_nowait(payload(event, total))
        except queue.Full:
            self.status = 'n8n: demasiados avisos sin enviar; se descartan los nuevos'

    def post(self, row):
        """Envía la fila y devuelve lo que contesta n8n (un diccionario; vacío si no contesta JSON)."""
        request = urllib.request.Request(self.url, data=json.dumps(row).encode(), method='POST',
                                         headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            body = response.read()
        try:
            reply = json.loads(body or b'{}')
        except ValueError:
            reply = {}
        return reply if isinstance(reply, dict) else {}

    def note(self, ok, message):
        self.replies.append({'mensaje': message, 'at': time.time(), 'ok': bool(ok)})

    def run(self):
        row, failures = None, 0
        while not self.stop.is_set():
            if row is None:
                try:
                    row = self.pending.get(timeout=.5)
                except queue.Empty:
                    continue
            try:
                reply = self.post(row)
            except urllib.error.HTTPError as exc:
                # n8n contestó, pero con error: se reintenta poco (otra vez podría duplicar la fila) y se avisa.
                failures += 1
                if failures >= 3:
                    self.note(False, f'⚠️ n8n no pudo apuntar {row["residuo"]} (error {exc.code})')
                    self.status = f'n8n: error {exc.code}'
                    row, failures = None, 0
                else:
                    self.stop.wait(self.retry)
                continue
            except Exception as exc:
                # n8n cerrado o arrancando: se conserva y se reintenta en orden, sin límite.
                self.status = f'n8n no responde ({str(exc)[:60]}); {self.pending.qsize() + 1} pendiente(s)'
                self.stop.wait(self.retry)
                continue
            failures = 0
            ok = reply.get('ok', True) is not False
            self.note(ok, reply.get('mensaje') or f'n8n recibió: {row["residuo"]}')
            if ok:
                self.sent += 1
            self.status = f'n8n: {self.sent} residuo(s) apuntado(s)'
            row = None

    def summary(self):
        """Para el panel: estado y últimas respuestas."""
        return {'estado': self.status, 'enviados': self.sent, 'respuestas': list(self.replies)}

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
