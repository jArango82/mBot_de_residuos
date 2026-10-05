"""Detector local de papel pequeño con seguimiento automático entre análisis."""
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


class PaperDetector:
    def __init__(self,camera):
        self.camera=camera
        self.stop=threading.Event()
        self.latest=None
        self.status='Cargando detector de papel...'
        self.consumed=self.frame_stamp=None
        self.trackers=[]
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        try:
            from transformers import AutoProcessor,AutoModelForZeroShotObjectDetection
            import torch
            torch.set_num_threads(4)
            path=Path(__file__).resolve().parent/'models/grounding-dino-tiny'
            processor=AutoProcessor.from_pretrained(path,local_files_only=True)
            model=AutoModelForZeroShotObjectDetection.from_pretrained(path,local_files_only=True).eval()
            verifier=PaperVerifier()
            previous=[]
            previous_stamp=0
            self.status='Papel: verificacion visual activa'
            last_stamp=None
            while not self.stop.is_set():
                sample=self.camera.read()
                if sample is None or sample[1]==last_stamp:
                    self.stop.wait(.05)
                    continue
                frame,stamp=sample
                last_stamp=stamp
                inputs=processor(images=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),
                    text='a crumpled paper. a tissue. a bottle.',return_tensors='pt',
                    size={'shortest_edge':384,'longest_edge':640})
                with torch.inference_mode():
                    outputs=model(**inputs)
                result=processor.post_process_grounded_object_detection(outputs,inputs.input_ids,
                    threshold=.32,text_threshold=.25,target_sizes=[frame.shape[:2]])[0]
                verified=[(box,score) for box,score in paper_boxes(result,frame.shape)
                          if verifier.check(frame,box)[0]]
                # Dos análisis independientes: no etiquetar una aparición aislada.
                confirmed=[(box,score) for box,score in verified
                           if stamp-previous_stamp<4 and any(overlap(box,oldbox)>.35 for oldbox,_ in previous)]
                previous,previous_stamp=verified,stamp
                self.latest=(confirmed,frame,stamp)
                self.status='Papel: doble verificacion; ambiguos sin etiqueta'
                self.stop.wait(.1)
        except Exception as exc:
            self.status='Papel no disponible: '+str(exc)

    def read(self,frame,stamp):
        result=self.latest
        if result is not None and result[2]!=self.consumed:
            boxes,source,source_stamp=result
            self.consumed=source_stamp
            self.trackers=[]
            if 0 <= stamp-source_stamp < 4:
                for box,score in boxes:
                    x1,y1,x2,y2=box.astype(int)
                    tracker=cv2.TrackerCSRT_create()
                    tracker.init(source,(x1,y1,x2-x1,y2-y1))
                    self.trackers.append((tracker,score,source_stamp,(x2-x1)*(y2-y1),box))
        if stamp!=self.frame_stamp:
            self.frame_stamp=stamp
            retained=[]
            for tracker,score,observed,area,oldbox in self.trackers:
                if not 0 <= stamp-observed < 4:
                    continue
                ok,(x,y,w,h)=tracker.update(frame)
                if ok and .6*area < w*h < 1.6*area and x>=0 and y>=0 and x+w<frame.shape[1] and y+h<frame.shape[0]:
                    retained.append((tracker,score,observed,area,np.array([x,y,x+w,y+h])))
            self.trackers=retained
        return [(b.astype(int).tolist(),'papel / servilleta',s,stamp-t)
                for _,s,t,_,b in self.trackers]
