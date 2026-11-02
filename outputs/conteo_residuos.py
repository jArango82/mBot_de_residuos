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

SIZE = 400.   # el recuadro, visto desde arriba, en coordenadas propias (como la navegación)


def covered(box, other):
    """Fracción de la caja [x1, y1, x2, y2] que cae dentro de la otra."""
    w = max(0., min(box[2], other[2]) - max(box[0], other[0])); h = max(0., min(box[3], other[3]) - max(box[1], other[1]))
    return w * h / max(1e-6, (box[2] - box[0]) * (box[3] - box[1]))


class SeparationCounter:
    """Cuenta un residuo cuando su posición pasa de dentro del recuadro a completamente fuera.

    Las posiciones se miden en coordenadas del recuadro (homografía de sus esquinas a un cuadrado de 400), no en
    píxeles: si la cámara se mueve, el recuadro y el residuo se mueven igual y la posición no cambia. Así se
    recuerda la posición de dentro aunque el recuadro deje de verse un rato, o el residuo quede tapado por el
    robot mientras lo empuja, y se cuenta en cuanto se ve fuera. Si sale por un lado que da al borde de la
    imagen (no hay «fuera» visible), se cuenta cuando desaparece por ese lado."""
    def __init__(self, store, session=None):
        self.store=store;self.session=session or store.session()
        self.tracks=[];self.next_id=1;self.zone=None;self.zone_time=-1e9;self.sheets={}
    def reset_zone(self):
        """La cinta se eligió de nuevo: las posiciones de antes ya no valen."""
        self.zone=None
        for t in self.tracks:
            t.update(inside=False,zone=None,hits=0)
    @staticmethod
    def plane_of(polygon):
        return cv2.getPerspectiveTransform(np.float32(polygon),np.float32([[0,0],[SIZE,0],[SIZE,SIZE],[0,SIZE]]))
    @staticmethod
    def to_plane(points, matrix):
        return cv2.perspectiveTransform(np.float32(points).reshape(-1,1,2),matrix).reshape(-1,2)
    @classmethod
    def region(cls, box, matrix, shape=None):
        x1,y1,x2,y2=box
        quad=cls.to_plane([[x1,y1],[x2,y1],[x2,y2],[x1,y2]],matrix)
        center=cls.to_plane([[(x1+x2)/2,(y1+y2)/2]],matrix)[0]
        # Distancia del centro al borde: positiva dentro, negativa fuera (10 unidades = 5 px en un recuadro de 200).
        inside=float(min(center[0],center[1],SIZE-center[0],SIZE-center[1]))
        square=np.float32([[0,0],[SIZE,0],[SIZE,SIZE],[0,SIZE]])
        area,_=cv2.intersectConvexConvex(np.float32(quad),square) if cv2.isContourConvex(np.float32(quad)) else (1.,None)
        # Fuera: el centro pasó la cinta y como mucho una cuarta parte del residuo queda aún dentro (encima de la
        # cinta). Exigir que no quedara nada dentro dejaba sin contar residuos que, a la vista, ya habían salido.
        if area < .25*max(cv2.contourArea(np.float32(quad)),1) and inside < -10: return 'out',center
        if inside > 10: return 'in',center
        if shape is not None and (x1<=3 or y1<=3 or x2>=shape[1]-3 or y2>=shape[0]-3):
            # Cortado por el borde de la imagen sobre la cinta: lo que se ve es solo su parte de dentro. Si al otro lado
            # de la cinta ya no hay imagen, el resto está fuera.
            distances=[center[0],SIZE-center[0],center[1],SIZE-center[1]];k=int(np.argmin(distances))
            outward=np.array([[-1,0],[1,0],[0,-1],[0,1]][k],float)
            beyond=cls.to_plane([center+outward*(distances[k]+30)],np.linalg.inv(matrix))[0]
            if not (0<=beyond[0]<shape[1] and 0<=beyond[1]<shape[0]): return 'out',center
        return 'edge',center
    def update(self, objects, polygon, visible, now, shape=None, robot=None, sheets=None):
        """shape: tamaño de la imagen (para saber qué lados del recuadro dan al borde de la imagen).
        robot: caja [x1, y1, x2, y2] del robot; un residuo tapado por él no ha desaparecido.
        sheets: {etiqueta: cuadrilátero en el plano} de la hoja a la que va cada clase. Para esas clases no se cuenta
        la salida del recuadro, sino que quede sobre su hoja (habiendo estado antes fuera de ella)."""
        self.sheets = sheets or {}
        self.tracks=[t for t in self.tracks if now-t['seen']<60]
        if not visible or polygon is None:
            # Sin recuadro visible no se sabe dónde está cada cosa respecto a él: se conserva lo sabido.
            return []
        polygon=np.asarray(polygon,np.float32)
        matrix=self.plane_of(polygon)
        jumped=None
        if self.zone is not None and np.max(np.linalg.norm(polygon-self.zone,axis=1))>20 and now-self.zone_time<1:
            # El recuadro saltó entre dos imágenes seguidas. Si fue la cámara, los residuos se movieron igual; si
            # fue la detección de la cinta, no: entonces no se puede comparar la posición de antes con la de ahora.
            jumped=cv2.getPerspectiveTransform(self.zone,polygon)
        self.zone=polygon.copy();self.zone_time=now
        used=set();emitted=[]
        # Solo muestras nuevas del detector; el mismo resultado mostrado 30 veces no confirma nada.
        for obj in sorted(objects,key=lambda o:o['confidence'],reverse=True):
            if not obj.get('countable', True) or obj['label']=='objeto por identificar':
                continue
            # Papel, envolturas y cajas los reconoce DINO cada uno o dos segundos, no en cada imagen.
            slow_detector = obj['label'].startswith(('papel','envoltura','caja'))
            if obj.get('observation_age',0) > (4 if slow_detector else 1.5): continue
            observed=round(now-obj.get('observation_age',0),3)
            box=np.asarray(obj['box'],float);image=(box[:2]+box[2:])/2
            region,center=self.region(box,matrix,shape)
            candidates=[]
            for i,t in enumerate(self.tracks):
                if i in used or t['label']!=obj['label']: continue
                gap=now-t['seen'];distance=float(np.linalg.norm(center-t['center']))
                # Visto solo un par de veces y hace rato (al colocarlo a mano, de paso): no hereda la identidad. (2/11:
                # el blanqueador llevado a su hoja reapareció junto a una detección suelta de hacía 50 s, tomó su
                # identidad, que nunca se había visto fuera de la hoja, y no se contó.)
                if t.get('obs',0)<3 and gap>5: continue
                # Empujado por el robot puede quedar tapado varios segundos y aparecer más lejos.
                if distance<min(220,50+150*gap):
                    candidates.append((distance,i))
            # Una pista vista hace poco (tapada por el robot al empujar) antes que otra de hace mucho en el mismo sitio
            # (2/11: el blanqueador llevado a la hoja roja heredaba la pista de cuando se colocó allí a mano 50 s antes,
            # que nunca había estado fuera de la hoja, y no se contaba).
            if any(now-self.tracks[i]['seen']<10 for _,i in candidates):
                candidates=[(d,i) for d,i in candidates if now-self.tracks[i]['seen']<10]
            candidates.sort()
            if len(candidates)>1 and candidates[1][0]-candidates[0][0]<24:
                # Cruce ambiguo de dos objetos semejantes: no inventar identidad.
                for _,i in candidates: self.tracks[i]['inside']=False
                continue
            if candidates:
                _,idx=candidates[0];t=self.tracks[idx];used.add(idx)
                if observed<=t['observed']+.02: continue
                if now-t['seen']>3:
                    t['spot']=None          # reaparece: dónde está ahora se mira como una llegada nueva
                if jumped is not None and now-t['seen']<1:
                    expected=cv2.perspectiveTransform(np.float32(t['image']).reshape(1,1,2),jumped).reshape(2)
                    if np.linalg.norm(expected-image)>25:
                        t.update(inside=False,zone=None,hits=0)
            else:
                t=dict(id=self.next_id,label=obj['label'],counted=False,inside=False,zone=None,hits=0,observed=-1)
                self.next_id+=1;self.tracks.append(t);used.add(len(self.tracks)-1)
            if region!=t['zone']:
                t.update(zone=region,hits=1,since=now)
            else: t['hits']+=1
            t.update(box=box,image=image,center=center,seen=now,observed=observed,obs=t.get('obs',0)+1)
            obj['track_id']=t['id']
            if t['label'] in self.sheets:
                emitted+=self.placement(t,center,now,obj['confidence'])
                continue
            if t['hits']>=2 and now-t['since']>=.35:
                if region=='in': t['inside']=True
                if region=='in' and t['counted'] and now-t['since']>=2:
                    # Lo devolvieron al recuadro (y sigue dentro 2 s, no es el temblor del borde): otra salida contará.
                    t.update(counted=False,id=self.next_id);self.next_id+=1
                if region=='out' and t['inside'] and not t['counted']:
                    emitted+=self.count(t,obj['confidence'])
        for t in self.tracks:
            # Sobre su hoja y, durante un segundo, en ningún otro sitio (el robot lo tapa al dejarlo): cuenta.
            if t['label'] in self.sheets and t.get('spot')=='goal' and t.get('away') and not t.get('placed') and \
                    now-t['spot_since']>=1:
                emitted+=self.place(t,.5)
        for t in self.tracks:
            if t['label'] in self.sheets: continue
            # El robot lo sacó empujándolo y desde entonces no ha vuelto a verse dentro: fuera del recuadro el detector
            # a veces no lo encuentra (junto a los muebles, en sombra), pero el robot sí sabe que lo pasó de la cinta.
            if t.get('pushed') and t['inside'] and not t['counted'] and now-t['pushed']>=2 and \
                    not (t['zone']=='in' and t['seen']>t['pushed']+.5):
                emitted+=self.count(t,.5)
        for t in self.tracks:
            if t['label'] in self.sheets: continue
            # Visto fuera y, durante un segundo, en ningún otro sitio: fuera de la cinta el detector lo pierde a menudo
            # (suelo oscuro, muebles), así que una sola posición nueva fuera basta si nada la contradice.
            if t['zone']=='out' and t['inside'] and not t['counted'] and now-t['since']>=1:
                emitted+=self.count(t,.5)
        if shape is not None:
            emitted+=self.left_view(matrix,shape,robot,now,used)
        return emitted
    def placement(self, t, center, now, confidence):
        """Llevado a su hoja: visto fuera de ella (confirmado) y después encima (2 observaciones en ≥ 0,35 s)."""
        goal=np.float32(self.sheets[t['label']])
        spot='goal' if cv2.pointPolygonTest(goal,(float(center[0]),float(center[1])),True)>-2 else 'off'
        if spot!=t.get('spot'):
            t.update(spot=spot,spot_hits=1,spot_since=now)
        else:
            t['spot_hits']+=1
        if t['spot_hits']<2 or now-t['spot_since']<.35:
            return []
        if spot=='off':
            t['away']=True
            # Lo quitaron de la hoja y sigue fuera de ella: si vuelve a dejarse encima, cuenta otra vez. Salvo si se
            # vio fuera enseguida de contarlo (< 5 s): no había llegado (2/11: visto un instante sobre la hoja mientras
            # el robot lo empujaba y tapaba, contado, y otra vez al dejarlo de verdad).
            if t.get('placed') and now-t['spot_since']>=2 and t['spot_since']-t.get('placed_at',-1e9)>=5:
                t.update(placed=False,id=self.next_id);self.next_id+=1
            return []
        if not t.get('away') and now-t['spot_since']<2:
            # Recién aparecido sobre su hoja sin haberse visto fuera: si otro igual que sí estaba fuera dejó de verse hace
            # poco cerca de aquí (tapado por el robot al empujarlo), es el mismo residuo con otra identidad.
            donors=[o for o in self.tracks if o is not t and o['label']==t['label'] and o.get('away') and
                    not o.get('placed') and .3<now-o['seen']<15 and np.linalg.norm(o['center']-center)<250]
            if donors:
                t['away']=True
                for o in donors: o['placed']=True
        return self.place(t,confidence) if t.get('away') and not t.get('placed') else []
    def place(self, t, confidence):
        t['placed']=True;t['placed_at']=t['seen']
        return [t['id']] if self.store.record(self.session,t['id'],t['label'],confidence) else []
    def pushed_out(self, label, point, now):
        """El robot dice que sacó un residuo de esa clase por ese punto de la cinta (coordenadas del recuadro)."""
        options=[t for t in self.tracks if t['inside'] and not t['counted'] and (label is None or t['label']==label)
                 and np.linalg.norm(t['center']-np.asarray(point,float))<150]
        if options:
            min(options,key=lambda t:np.linalg.norm(t['center']-np.asarray(point,float)))['pushed']=now
    def count(self, t, confidence):
        t['counted']=True
        return [t['id']] if self.store.record(self.session,t['id'],t['label'],confidence) else []
    def left_view(self, matrix, shape, robot, now, seen):
        """Residuos que estaban dentro junto a un lado que da al borde de la imagen y ya no se ven: salieron por ahí
        (fuera de ese lado no hay imagen donde verlos)."""
        h,w=shape[:2];back=np.linalg.inv(matrix);emitted=[]
        for i,t in enumerate(self.tracks):
            if i in seen or not t['inside'] or t['counted'] or now-t['seen']<1.5:
                continue
            p=t['center'];distances=[p[0],SIZE-p[0],p[1],SIZE-p[1]];k=int(np.argmin(distances))
            if distances[k]>70: continue
            outward=np.array([[-1,0],[1,0],[0,-1],[0,1]][k],float)
            beyond=self.to_plane([p+outward*(distances[k]+40)],back)[0]
            if 5<=beyond[0]<w-5 and 5<=beyond[1]<h-5: continue        # fuera de ese lado sí hay imagen
            if robot is not None and covered(t['box'],robot)>.3: continue   # tapado por el robot, no desaparecido
            emitted+=self.count(t,.5)
        return emitted
