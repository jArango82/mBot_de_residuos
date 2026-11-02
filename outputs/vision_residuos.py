"""Detección a varias escalas y persistencia breve de objetos observados."""
import threading
import numpy as np

# Al cargar DINO, transformers crea pesos vacíos («meta») para todo el proceso; si YOLO se
# construye a la vez en otro hilo queda inservible. Los modelos se cargan de uno en uno.
MODEL_LOCK = threading.Lock()


# Botellas que el detector propio distingue (1/11): cada una va a su hoja, no se juntan en «botella».
TRAINED_BOTTLES = ('botella de vidrio', 'botella de plastico')
# Ante la duda entre un residuo y otro peligroso que se le parece, se trata como peligroso: un envase de
# blanqueador en la hoja de aprovechables es peor que una botella de agua en la de peligrosos.
CAUTION = {'botella de plastico': 'envase de blanqueador'}


def category(name):
    if name == 'tapa de botella':
        return 'objeto por identificar'  # Se confunde con rollos y envolturas pequeñas.
    if name.startswith('botella') and name not in TRAINED_BOTTLES:
        return 'botella'
    if name.startswith('papel'):
        return 'papel / servilleta'
    return name


def overlap(a,b):
    a,b=np.asarray(a,float),np.asarray(b,float)
    size=np.maximum(0,np.minimum(a[2:],b[2:])-np.maximum(a[:2],b[:2]))
    inter=float(size.prod())
    union=float(np.maximum(0,a[2:]-a[:2]).prod()+np.maximum(0,b[2:]-b[:2]).prod()-inter)
    return inter/max(union,1)


def multiscale(model,frame,ids):
    height,width=frame.shape[:2]
    tile=min(320,height,width)
    xs=sorted(set([0,(width-tile)//2,width-tile]))
    ys=sorted(set([0,height-tile]))
    regions=[(0,0,width,height)]+[(x,y,tile,tile) for y in ys for x in xs]
    images=[frame[y:y+h,x:x+w] for x,y,w,h in regions]
    results=model.predict(images,imgsz=640,conf=.18,classes=ids,device='cpu',verbose=False)
    detections=[]
    for index,(result,(x,y,w,h)) in enumerate(zip(results,regions)):
        for item in result.boxes:
            b=item.xyxy[0].cpu().numpy()
            if index and ((x>0 and b[0]<6) or (y>0 and b[1]<6) or
                          (x+w<width and b[2]>w-6) or (y+h<height and b[3]>h-6)):
                continue  # Las otras ventanas cubren objetos cortados por este recorte.
            b=b+np.array([x,y,x,y])
            detections.append((b,category(model.names[int(item.cls.item())]),float(item.conf.item())))
    unique=[]
    for item in sorted(detections,key=lambda d:d[2],reverse=True):
        if not any(overlap(item[0],prior[0])>.45 for prior in unique):
            unique.append(item)
    return unique


# Un objeto nuevo exige 0,25; uno que ya se sigue se mantiene desde 0,15. Esta histéresis evita
# que una caja aparezca y desaparezca cuando la puntuación oscila alrededor del umbral.
NEW_CONF = .25
KEEP_CONF = .15
AMBIGUOUS = 'objeto por identificar'


class StableObjects:
    """Persistencia breve con histéresis y voto de etiqueta, para que no parpadee ni cambie de nombre."""
    def __init__(self,hold=.7,new_conf=NEW_CONF):
        self.tracks=[]
        self.hold=hold
        self.new_conf=new_conf

    def update(self,detections,stamp):
        self.tracks=[t for t in self.tracks if 0 <= stamp-t['seen'] <= self.hold]
        used=set()
        for box,name,confidence in sorted(detections,key=lambda d:d[2],reverse=True):
            name=category(name)
            # Misma etiqueta: basta un solape pequeño. Otra etiqueta: debe ser casi la misma caja.
            options=[(overlap(box,t['box']),i) for i,t in enumerate(self.tracks) if i not in used]
            options=[(score,i) for score,i in options if score>(.2 if self.tracks[i]['name']==name else .5)]
            score,index=max(options,default=(0,-1))
            if index>=0:
                track=self.tracks[index]
                track['box']=.35*track['box']+.65*np.asarray(box,float)
                # El nombre mostrado es el más votado recientemente, no el de la última imagen.
                track['votes']={label:.85*value for label,value in track['votes'].items()}
                track['votes'][name]=track['votes'].get(name,0)+confidence
                track['name']=cautious(track['votes'])
                track['confidence']=.4*track['confidence']+.6*confidence
                track['seen']=stamp
                track['hits']+=1
                track['confirmed']|=track['hits']>=2 and confidence>=self.new_conf
                used.add(index)
            elif confidence>=self.new_conf:
                self.tracks.append({'box':np.asarray(box,float),'name':name,'votes':{name:confidence},
                                    'confidence':confidence,'seen':stamp,'hits':1,'confirmed':confidence>=.60})
                used.add(len(self.tracks)-1)
        return [(t['box'].astype(int).tolist(),t['name'],t['confidence'],stamp-t['seen'])
                for t in self.tracks if t['confirmed']]


def cautious(votes):
    """La etiqueta más votada, salvo que el voto de su pareja peligrosa llegue a la mitad: entonces la peligrosa."""
    name=max(votes,key=votes.get)
    risky=CAUTION.get(name)
    return risky if risky and votes.get(risky,0)>=.5*votes[name] else name


def one_label(items, same=.6):
    """Una detección por objeto: el detector propio puede dar dos clases casi en la misma caja (plástico 0,45 y
    blanqueador 0,30). Se queda la más segura, salvo si la otra es su pareja peligrosa: entonces la peligrosa con
    la confianza mayor de las dos."""
    kept=[]
    for box,name,confidence in sorted(items,key=lambda d:d[2],reverse=True):
        twin=next((k for k,(b,n,c) in enumerate(kept) if n!=name and overlap(box,b)>=same),None)
        if twin is None:
            kept.append((box,name,confidence))
        elif CAUTION.get(kept[twin][1])==name:
            kept[twin]=(kept[twin][0],name,kept[twin][2])
    return kept


def small_enough(items, shape, share=.15):
    """Quita cajas que ocupan más de esa parte de la imagen. Los residuos reales vistos ocupaban hasta
    un 7 %; el modelo propio marcaba como caja zonas de suelo del 12-30 % en imágenes de otra cámara."""
    h,w=shape[:2]
    return [item for item in items if float(np.prod(np.maximum(0,np.asarray(item[0][2:],float)-item[0][:2])))<=share*w*h]


def outside_zone(items, zone, shape, share=.6):
    """Quita cajas que caen casi enteras en una zona fija (proporciones de la imagen)."""
    if zone is None:
        return list(items)
    h,w=shape[:2]
    area=np.array([zone[0]*w,zone[1]*h,zone[2]*w,zone[3]*h])
    kept=[]
    for item in items:
        box=np.asarray(item[0],float)
        size=np.maximum(0,np.minimum(box[2:],area[2:])-np.maximum(box[:2],area[:2]))
        if size.prod() < share*max(float(np.maximum(0,box[2:]-box[:2]).prod()),1):
            kept.append(item)
    return kept


def merge_observations(general, specialized):
    """Un objeto no aparece dos veces por proceder de dos modelos. Papel o envoltura del especialista
    sustituye a la etiqueta general, pero una propuesta ambigua no tapa una detección concreta."""
    specialized=[s for s in specialized if s[1]!=AMBIGUOUS or
                 not any(g[1]!=AMBIGUOUS and overlap(s[0],g[0])>.35 for g in general)]
    return [item for item in general if not any(overlap(item[0],other[0])>.35 for other in specialized)] + list(specialized)
