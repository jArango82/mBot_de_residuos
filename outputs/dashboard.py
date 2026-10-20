#!/usr/bin/env python3
"""Dashboard de solo lectura, local, sin dependencias web ni datos simulados."""
import argparse
import csv
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import threading
from urllib.parse import urlparse, parse_qs
from conteo_residuos import EventStore, DEFAULT_DB

PAGE=Path(__file__).resolve().parent/'dashboard/index.html'

def serve(store, port=8765):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed=urlparse(self.path)
            sid=parse_qs(parsed.query).get('session',[None])[0]
            if parsed.path=='/': body=PAGE.read_bytes();kind='text/html; charset=utf-8'
            elif parsed.path in ('/api/estado','/exportar.csv'):
                report=store.report(sid)
                if parsed.path.endswith('.csv'):
                    text=io.StringIO();w=csv.writer(text)
                    w.writerow(['sesion','objeto','categoria','fecha_utc','confianza_detector'])
                    from datetime import datetime, timezone
                    for e in report['events']:
                        category=e['category']
                        if category.startswith(('=','+','-','@')): category="'"+category
                        w.writerow([e['session'],e['track'],category,datetime.fromtimestamp(e['at'],timezone.utc).isoformat(),e['confidence']])
                    body=('\ufeff'+text.getvalue()).encode();kind='text/csv; charset=utf-8'
                else: body=json.dumps(report,allow_nan=False).encode();kind='application/json'
            else: self.send_error(404);return
            self.send_response(200)
            self.send_header('Content-Type',kind)
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
            if kind.startswith('text/csv'): self.send_header('Content-Disposition','attachment; filename="residuos.csv"')
            self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        def log_message(self,*args): pass
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    return server

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--puerto',type=int,default=8765);p.add_argument('--db',type=Path,default=DEFAULT_DB)
    a=p.parse_args();server=serve(EventStore(a.db),a.puerto)
    print(f'Dashboard: http://127.0.0.1:{server.server_port} — Ctrl+C para cerrar',flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt: pass
    finally: server.shutdown();server.server_close()
if __name__=='__main__': main()
