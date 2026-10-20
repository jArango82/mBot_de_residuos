"""Papel y envolturas pequeñas: reconocimiento con giros y seguimiento local."""
from pathlib import Path
import threading
import time
import cv2
import numpy as np
from vision_residuos import overlap


class PaperVerifier:
    """Exige que papel supere alternativas visuales; permite no clasificar."""
    descriptions=[
        'crumpled paper or a used paper tissue','a paper sheet or paper napkin',
        'a plastic lid or plastic food container','a plastic bag or plastic packaging',
        'aluminum foil or a metal object','a glass bottle or plastic bottle',
        'wooden furniture','floor tiles or stone','fabric or clothing','a hand',
        'cardboard','a rubber eraser','an unknown object']

    def __init__(self):
        import clip
        import torch
        self.torch=torch
        path=Path(__file__).resolve().parent/'models/clip/ViT-B-32.pt'
        self.model,self.preprocess=clip.load(str(path),device='cpu')
        with torch.inference_mode():
            features=self.model.encode_text(clip.tokenize(['a photo of '+s for s in self.descriptions]))
            self.features=features/features.norm(dim=-1,keepdim=True)

    wrapper_descriptions=[
        'a crumpled candy wrapper','a plastic food wrapper','a shiny snack wrapper',
        'a piece of paper or a tissue','a plastic bottle','an aluminum can','a chair or furniture',
        'a brick floor or tiles','black adhesive tape on the floor','a hand','a shoe','a leaf','an unknown object']

    def wrapper_features(self):
        if not hasattr(self,'_wrapper_features'):
            import clip
            with self.torch.inference_mode():
                features=self.model.encode_text(clip.tokenize(['a photo of '+s for s in self.wrapper_descriptions]))
                self._wrapper_features=features/features.norm(dim=-1,keepdim=True)
        return self._wrapper_features

    def check_wrapper(self,frame,box):
        from PIL import Image
        x1,y1,x2,y2=np.asarray(box,float)
        padding=max(8,(x2-x1)*.3,(y2-y1)*.3)
        crop=frame[max(0,int(y1-padding)):min(frame.shape[0],int(y2+padding)),
                   max(0,int(x1-padding)):min(frame.shape[1],int(x2+padding))]
        if crop.size==0: return False,0.,0.
        # Promediar cuatro giros evita que la verificación dependa de cómo esté orientado el recorte.
        images=self.torch.stack([self.preprocess(Image.fromarray(cv2.cvtColor(np.rot90(crop,k).copy(),cv2.COLOR_BGR2RGB)))
                                 for k in range(4)])
        with self.torch.inference_mode():
            features=self.model.encode_image(images)
            features=features/features.norm(dim=-1,keepdim=True)
            similarities=(features@self.wrapper_features().T).mean(0)
        wrapper=float(similarities[:3].max());other=float(similarities[3:].max())
        return wrapper>=.23 and wrapper-other>=.004,wrapper,other

    def check(self,frame,box):
        from PIL import Image
        x1,y1,x2,y2=np.asarray(box,float)
        padding=max(8,(x2-x1)*.3,(y2-y1)*.3)
        x1,y1=max(0,int(x1-padding)),max(0,int(y1-padding))
        x2,y2=min(frame.shape[1],int(x2+padding)),min(frame.shape[0],int(y2+padding))
        if x2<=x1 or y2<=y1:
            return False,0.,0.
        crop=Image.fromarray(cv2.cvtColor(frame[y1:y2,x1:x2],cv2.COLOR_BGR2RGB))
        with self.torch.inference_mode():
            features=self.model.encode_image(self.preprocess(crop).unsqueeze(0))
            features=features/features.norm(dim=-1,keepdim=True)
            similarities=(features@self.features.T)[0]
        paper=float(similarities[:2].max())
        other=float(similarities[2:].max())
        # Son similitudes comparativas, no probabilidades calibradas.
        return paper>=.25 and paper-other>=.005,paper,other


def paper_boxes(result,shape):
    height,width=shape[:2]
    found=[]
    for box,label,score in zip(result['boxes'],result['text_labels'],result['scores']):
        if not any(word in label for word in ('paper','tissue','napkin')):
            continue
        b=np.asarray(box.cpu(),float)
        b[[0,2]]=np.clip(b[[0,2]],0,width-1)
        b[[1,3]]=np.clip(b[[1,3]],0,height-1)
        area=(b[2]-b[0])*(b[3]-b[1])
        if min(b[2:]-b[:2])<10 or area>width*height*.2:
            continue  # Rechaza suelo entero etiquetado como papel.
        found.append((b,float(score)))
    distinct=[]
    for b,score in sorted(found,key=lambda item:item[1],reverse=True):
        if not any(overlap(b,prior[0])>.3 for prior in distinct):
            distinct.append((b,score))
    return distinct


def restore_box(box, shape, turns):
    """Devuelve coordenadas de una imagen np.rot90 al fotograma original."""
    h,w=shape[:2];x1,y1,x2,y2=np.asarray(box,float)
    points=np.array([[x1,y1],[x2,y1],[x2,y2],[x1,y2]])
    x,y=points[:,0].copy(),points[:,1].copy()
    if turns%4==1: points=np.c_[w-y,x]
    elif turns%4==2: points=np.c_[w-x,h-y]
    elif turns%4==3: points=np.c_[y,h-x]
    result=np.r_[points.min(axis=0),points.max(axis=0)]
    result[[0,2]]=np.clip(result[[0,2]],0,w-1)
    result[[1,3]]=np.clip(result[[1,3]],0,h-1)
    return result


def small_candidates(result, shape):
    h,w=shape[:2];found=[]
    for box,label,score in zip(result['boxes'],result['text_labels'],result['scores']):
        score=float(score);label=label.lower()
        kind=('envoltura' if ('wrapper' in label or 'snack bag' in label) else
              'papel / servilleta' if any(word in label for word in ('paper','tissue','napkin')) else None)
        if kind is None or score < (.28 if kind=='envoltura' else .32): continue
        b=np.asarray(box.cpu() if hasattr(box,'cpu') else box,float)
        if min(b[2:]-b[:2])<10 or np.prod(b[2:]-b[:2])>w*h*.2: continue
        if kind=='envoltura' and (b[0]<2 or b[1]<2 or b[2]>w-2 or b[3]>h-2): continue
        b[[0,2]]=np.clip(b[[0,2]],0,w-1);b[[1,3]]=np.clip(b[[1,3]],0,h-1)
        found.append((b,kind,score))
    # Evitar verificar muchas cajas anidadas del mismo candidato.
    unique=[]
    for item in sorted(found,key=lambda v:v[2],reverse=True):
        if not any(overlap(item[0],old[0])>.3 for old in unique): unique.append(item)
    return unique


class SmallWasteRecognizer:
    def __init__(self):
        from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
        import torch
        self.torch=torch
        torch.set_num_threads(4)
        path=Path(__file__).resolve().parent/'models/grounding-dino-tiny'
        self.processor=AutoProcessor.from_pretrained(path,local_files_only=True)
        self.model=AutoModelForZeroShotObjectDetection.from_pretrained(path,local_files_only=True).eval()
        self.verifier=PaperVerifier()

    def detect(self,frame,turns=0):
        view=np.rot90(frame,turns).copy()
        inputs=self.processor(images=cv2.cvtColor(view,cv2.COLOR_BGR2RGB),
            text='a crumpled paper. a tissue. a candy wrapper. a crumpled plastic wrapper. a snack bag. a bottle.',
            return_tensors='pt',size={'shortest_edge':512,'longest_edge':768})
        with self.torch.inference_mode(): outputs=self.model(**inputs)
        result=self.processor.post_process_grounded_object_detection(outputs,inputs.input_ids,
            threshold=.28,text_threshold=.25,target_sizes=[view.shape[:2]])[0]
        verified=[]
        for box,name,score in small_candidates(result,view.shape):
            original=restore_box(box,frame.shape,turns)
            # Verificar antes de redondear/remapear conserva el mismo recorte en todos los giros.
            valid=(self.verifier.check_wrapper(view,box)[0] if name=='envoltura'
                   else self.verifier.check(frame,original)[0])
            if valid: verified.append((original,name,score))
        return verified


class PaperDetector:
    """Nombre conservado por compatibilidad; también reconoce envolturas."""
    def __init__(self,camera):
        self.camera=camera
        self.stop=threading.Event()
        self.latest=None
        self.status='Cargando papel y envolturas...'
        self.consumed=self.frame_stamp=None
        self.trackers=[]
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        try:
            recognizer=SmallWasteRecognizer()
            history=[];previous=[];previous_stamp=0
            preferred=misses=0
            last_stamp=None
            self.status='Papel y envolturas: buscando con varias orientaciones'
            while not self.stop.is_set():
                sample=self.camera.read()
                if sample is None or sample[1]==last_stamp:
                    self.stop.wait(.05);continue
                frame,stamp=sample;last_stamp=stamp
                # Escanear giros si falta la envoltura y conservar la orientación que funciona.
                turns=(preferred+misses)%4
                verified=recognizer.detect(frame,turns)
                if any(n=='envoltura' for _,n,_ in verified): preferred=turns;misses=0
                else: misses+=1
                history=[(t,boxes) for t,boxes in history if stamp-t<6]
                confirmed=[]
                for box,name,score in verified:
                    prior=[item for _,items in history for item in items] if name=='envoltura' else (previous if stamp-previous_stamp<6 else [])
                    if any(oldname==name and overlap(box,oldbox)>.35 for oldbox,oldname,_ in prior):
                        confirmed.append((box,name,score))
                history.append((stamp,verified));previous,previous_stamp=verified,stamp
                self.latest=(confirmed,frame,stamp)
                self.status='Papel y envolturas: giros + verificacion visual'
                self.stop.wait(.1)
        except Exception as exc:
            self.status='Papel/envolturas no disponible: '+str(exc)

    @staticmethod
    def lifetime(name): return 6 if name=='envoltura' else 4

    def read(self,frame,stamp):
        result=self.latest
        if result is not None and result[2]!=self.consumed:
            boxes,source,source_stamp=result;self.consumed=source_stamp
            # Un análisis sin resultados no borra instantáneamente un seguimiento aún reciente.
            for box,name,score in boxes:
                if not 0 <= stamp-source_stamp < self.lifetime(name): continue
                self.trackers=[t for t in self.trackers if overlap(t[4],box)<.35]
                x1,y1,x2,y2=box.astype(int)
                tracker=cv2.TrackerCSRT_create()
                tracker.init(source,(x1,y1,x2-x1,y2-y1))
                self.trackers.append((tracker,score,source_stamp,(x2-x1)*(y2-y1),box,name))
        if stamp!=self.frame_stamp:
            self.frame_stamp=stamp;retained=[]
            for tracker,score,observed,area,oldbox,name in self.trackers:
                if not 0 <= stamp-observed < self.lifetime(name): continue
                ok,(x,y,w,h)=tracker.update(frame)
                if ok and .6*area < w*h < 1.6*area and x>=0 and y>=0 and x+w<frame.shape[1] and y+h<frame.shape[0]:
                    retained.append((tracker,score,observed,area,np.array([x,y,x+w,y+h]),name))
            self.trackers=retained
        return [(b.astype(int).tolist(),name,s,stamp-t) for _,s,t,_,b,name in self.trackers]
