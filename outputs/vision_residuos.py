"""Detección a varias escalas y persistencia breve de objetos observados."""
import numpy as np


def category(name):
    if name.startswith('botella'):
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


class StableObjects:
    def __init__(self,hold=.7):
        self.tracks=[]
        self.hold=hold

    def update(self,detections,stamp):
        self.tracks=[t for t in self.tracks if 0 <= stamp-t['seen'] <= self.hold]
        used=set()
        for box,name,confidence in sorted(detections,key=lambda d:d[2],reverse=True):
            name=category(name)
            options=[(overlap(box,t['box']),i) for i,t in enumerate(self.tracks)
                     if i not in used and t['name']==name]
            score,index=max(options,default=(0,-1))
            if score>.2:
                track=self.tracks[index]
                track['box']=.35*track['box']+.65*np.asarray(box,float)
                track['confidence']=.4*track['confidence']+.6*confidence
                track['seen']=stamp
                track['hits']+=1
                track['confirmed']|=track['hits']>=2 and confidence>=.25
                used.add(index)
            elif confidence>=.25:
                self.tracks.append({'box':np.asarray(box,float),'name':name,'confidence':confidence,
                                    'seen':stamp,'hits':1,'confirmed':confidence>=.60})
                used.add(len(self.tracks)-1)
        return [(t['box'].astype(int).tolist(),t['name'],t['confidence'],stamp-t['seen'])
                for t in self.tracks if t['confirmed']]
