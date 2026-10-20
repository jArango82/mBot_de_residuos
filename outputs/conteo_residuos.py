"""Conteo conservador por trayectorias dentro -> completamente fuera."""
from datetime import datetime, timezone
from pathlib import Path
import json
import sqlite3
from contextlib import contextmanager
import time
import uuid
import cv2
import numpy as np
from vision_residuos import overlap

DEFAULT_DB = Path(__file__).resolve().parents[1] / 'work/estadisticas.sqlite3'

class EventStore:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, started REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events(
                    session TEXT, track INTEGER, category TEXT, at REAL, confidence REAL,
                    PRIMARY KEY(session, track));
                CREATE TABLE IF NOT EXISTS live(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT);
            """)
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()
    def session(self):
        sid = uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?)', (sid, time.time()))
        return sid
    def record(self, sid, track, category, confidence):
        with self.connect() as db:
            cur = db.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)',
                            (sid,track,category,time.time(),float(confidence)))
            return cur.rowcount == 1
    def publish(self, state):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO live VALUES(1,?)', (json.dumps(state,allow_nan=False),))
    def report(self, sid=None):
        with self.connect() as db:
            sessions = [{'id':i,'started':t} for i,t in db.execute('SELECT * FROM sessions ORDER BY started DESC')]
            active = sessions[0]['id'] if sessions else None
            selected = sid or active
            rows = list(db.execute('SELECT session,track,category,at,confidence FROM events WHERE session=? ORDER BY at', (selected,)))
            total = db.execute('SELECT COUNT(*) FROM events').fetchone()[0]
            live = db.execute('SELECT payload FROM live WHERE id=1').fetchone()
        events = [{'session':s,'track':t,'category':c,'at':a,'confidence':f} for s,t,c,a,f in rows]
        categories = {}
        for e in events: categories[e['category']] = categories.get(e['category'],0)+1
        start = next((s['started'] for s in sessions if s['id']==selected),None)
        # La tasa termina en la última actualización de esa sesión, no sigue creciendo al cerrar.
        state = json.loads(live[0]) if live else {}
        end = state.get('updated',time.time()) if state.get('session')==selected else (events[-1]['at'] if events else start)
        elapsed = max(0,(end or 0)-start) if start is not None else 0
        return dict(sessions=sessions,selected=selected,active=active,total=len(events),historical_total=total,
                    categories=categories,events=events,elapsed=elapsed,
                    per_minute=len(events)/max(elapsed/60,1),live=state)

class SeparationCounter:
    def __init__(self, store, session=None):
        self.store=store;self.session=session or store.session()
        self.tracks=[];self.next_id=1;self.zone=None
    def reset_zone(self):
        self.zone=None
        for t in self.tracks:
            t.update(inside=False,zone=None,hits=0)
    @staticmethod
    def region(box, polygon):
        x1,y1,x2,y2=box
        center=((x1+x2)/2,(y1+y2)/2)
        distance=cv2.pointPolygonTest(polygon,center,True)
        rect=np.float32([[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
        area,_=cv2.intersectConvexConvex(rect,polygon)
        # No contar mientras alguna parte de la caja aún esté en el recinto.
        if area < .01 and distance < -5: return 'out'
        if distance > 5: return 'in'
        return 'edge'
    def update(self, objects, polygon, visible, now):
        if not visible or polygon is None:
            self.reset_zone()
            return []
        polygon=np.asarray(polygon,np.float32)
        if self.zone is not None and np.max(np.linalg.norm(polygon-self.zone,axis=1))>20:
            self.reset_zone()
        self.zone=polygon.copy()
        self.tracks=[t for t in self.tracks if now-t['seen']<6]
        used=set();emitted=[]
        # Solo muestras nuevas del detector; el mismo resultado mostrado 30 veces no confirma nada.
        for obj in sorted(objects,key=lambda o:o['confidence'],reverse=True):
            if not obj.get('countable', True) or obj['label']=='objeto por identificar':
                continue
            slow_detector = obj['label'].startswith(('papel','envoltura'))
            if obj.get('observation_age',0) > (4 if slow_detector else 1.5): continue
            observed=round(now-obj.get('observation_age',0),3)
            box=np.asarray(obj['box'],float);center=(box[:2]+box[2:])/2
            candidates=[]
            for i,t in enumerate(self.tracks):
                if i in used or t['label']!=obj['label']: continue
                gap=now-t['seen'];distance=float(np.linalg.norm(center-t['center']))
                if overlap(box,t['box'])>.1 or distance<min(100,25+100*gap):
                    candidates.append((distance,i))
            candidates.sort()
            if len(candidates)>1 and candidates[1][0]-candidates[0][0]<12:
                # Cruce ambiguo de dos objetos semejantes: no inventar identidad.
                for _,i in candidates: self.tracks[i]['inside']=False
                continue
            if candidates:
                _,idx=candidates[0];t=self.tracks[idx];used.add(idx)
                if observed<=t['observed']+.02: continue
                if now-t['seen']>(4 if slow_detector else 2.5): t.update(inside=False,zone=None,hits=0)
            else:
                t=dict(id=self.next_id,label=obj['label'],counted=False,inside=False,zone=None,hits=0,observed=-1)
                self.next_id+=1;self.tracks.append(t);used.add(len(self.tracks)-1)
            region=self.region(box,polygon)
            if region!=t['zone']:
                t.update(zone=region,hits=1,since=now)
            else: t['hits']+=1
            t.update(box=box,center=center,seen=now,observed=observed)
            obj['track_id']=t['id']
            if t['hits']>=2 and now-t['since']>=.35:
                if region=='in': t['inside']=True
                if region=='out' and t['inside'] and not t['counted']:
                    if self.store.record(self.session,t['id'],t['label'],obj['confidence']):
                        emitted.append(t['id'])
                    t['counted']=True
        return emitted
