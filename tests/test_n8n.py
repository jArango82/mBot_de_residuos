"""Envío de cada residuo separado a n8n: sin red real ni n8n, con un servidor local que hace de webhook."""
from pathlib import Path
import json, sys, tempfile, threading, time, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
from aviso_n8n import N8nSender, payload
from conteo_residuos import EventStore


class Webhook:
    def __init__(self, port=0, reply=None, code=200):
        rows=self.rows=[]
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                row=json.loads(self.rfile.read(int(self.headers['Content-Length']))); rows.append(row)
                self.send_response(code); self.end_headers()
                self.wfile.write(json.dumps(reply(row) if reply else {}).encode())
            def log_message(self,*a): pass
        self.server=HTTPServer(('127.0.0.1',port),Handler)
        self.port=self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
    def close(self): self.server.shutdown(); self.server.server_close()


def wait(condition, limit=5):
    end=time.time()+limit
    while time.time()<end and not condition(): time.sleep(.05)
    return condition()


class N8nTests(unittest.TestCase):
    def test_row_has_the_sheet_and_group(self):
        row=payload({'session':'abcdef123456','track':3,'category':'envase de blanqueador','at':0,'confidence':.873},4)
        self.assertEqual((row['residuo'],row['hoja'],row['grupo'],row['confianza'],row['total_sesion'],row['sesion']),
                         ('Envase de blanqueador','roja','peligrosos',.87,4,'abcdef12'))

    def test_each_new_waste_reaches_the_webhook_once(self):
        hook=Webhook(); tmp=tempfile.TemporaryDirectory()
        try:
            store=EventStore(Path(tmp.name)/'datos.db'); sid=store.session()
            sender=N8nSender(f'http://127.0.0.1:{hook.port}/webhook/residuos'); store.listeners.append(sender.send)
            store.record(sid,1,'lata',.9); store.record(sid,1,'lata',.9); store.record(sid,2,'caja de carton',.8)
            self.assertTrue(wait(lambda:len(hook.rows)==2))
            time.sleep(.3)
            self.assertEqual([(r['residuo'],r['hoja'],r['total_sesion']) for r in hook.rows],
                             [('Lata','amarilla',1),('Caja de cartón','amarilla',2)])
            sender.close()
        finally:
            hook.close(); tmp.cleanup()

    def test_waits_for_n8n_and_keeps_the_order(self):
        probe=Webhook(); port=probe.port; probe.close()          # puerto libre: n8n todavía cerrado
        sender=N8nSender(f'http://127.0.0.1:{port}/webhook/residuos',timeout=.5,retry=.2)
        event=lambda k,c:{'session':'s'*12,'track':k,'category':c,'at':time.time(),'confidence':.9}
        sender.send(event(1,'lata'),1); sender.send(event(2,'envase de blanqueador'),2)
        self.assertTrue(wait(lambda:'no responde' in sender.status))
        hook=Webhook(port)                                       # se abre n8n
        try:
            self.assertTrue(wait(lambda:len(hook.rows)==2))
            self.assertEqual([r['clase'] for r in hook.rows],['lata','envase de blanqueador'])
        finally:
            sender.close(); hook.close()


    def test_the_reply_of_n8n_is_kept_for_the_panel(self):
        # Como el flujo de n8n: contesta después de escribir en Google Sheets.
        hook=Webhook(reply=lambda r:{'ok':True,'mensaje':f"✅ Apuntado en Google Sheets: {r['residuo']} → hoja {r['hoja']}"})
        sender=N8nSender(f'http://127.0.0.1:{hook.port}/webhook/residuos')
        try:
            sender.send({'session':'s'*12,'track':1,'category':'lata','at':time.time(),'confidence':.9},1)
            self.assertTrue(wait(lambda:sender.sent==1))
            summary=sender.summary()
            self.assertEqual(summary['respuestas'][-1]['mensaje'],'✅ Apuntado en Google Sheets: Lata → hoja amarilla')
            self.assertTrue(summary['respuestas'][-1]['ok'])
        finally:
            sender.close(); hook.close()

    def test_a_failure_reported_by_n8n_is_shown_and_not_counted(self):
        hook=Webhook(reply=lambda r:{'ok':False,'mensaje':'⚠️ n8n no pudo apuntarlo en Google Sheets: sin permiso'})
        sender=N8nSender(f'http://127.0.0.1:{hook.port}/webhook/residuos')
        try:
            sender.send({'session':'s'*12,'track':1,'category':'lata','at':time.time(),'confidence':.9},1)
            self.assertTrue(wait(lambda:len(sender.replies)==1))
            self.assertFalse(sender.replies[-1]['ok']); self.assertEqual(sender.sent,0)
            self.assertEqual(len(hook.rows),1)                 # no se reintenta: podría duplicar la fila
        finally:
            sender.close(); hook.close()


if __name__=='__main__':unittest.main()
