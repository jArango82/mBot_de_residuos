"""Papel y envolturas pequeñas: reconocimiento con giros y seguimiento local."""
from pathlib import Path
import threading
import time
import cv2
import numpy as np
from vision_residuos import MODEL_LOCK, overlap
from vision_zoom import detail_sample, restore_crop, to_work


# «a bottle» no se acepta aquí: da a las botellas una descripción mejor que «envoltura» y las
# reconoce el detector general. «a cardboard box» sí se acepta: YOLO-World apenas ve cajas pequeñas
# (cajas de medicamento con 4-23 %), mientras que DINO las puntúa con 36-77 %.
PROMPT='a crumpled paper. a tissue. a candy wrapper. a crumpled plastic wrapper. a snack bag. a bottle. a cardboard box.'
ROUND_PROMPT='a bottle cap. a roll of adhesive tape. a cardboard box.'
# Robot sin etiqueta: en 46 fotogramas con la cámara en la mano, «a small robot car with tracks» lo marcó en
# todos (0,50-0,85). Las otras frases dan a cajas, papel, zapatos y cables una descripción mejor que «robot».
ROBOT_PROMPT='a small robot car with tracks. a cardboard box. a crumpled paper tissue. a shoe. a cable.'
ROBOT_SCORE=.45
# DINO y CLIP confunden papel blanco arrugado con un envoltorio. En las pruebas, la envoltura real
# tenía saturación media 43 y el papel/servilletas 3-15: sin color se verifica como papel.
COLORLESS=25


def colorless(image, box):
    x1,y1,x2,y2=(int(v) for v in box)
    crop=image[max(0,y1):max(0,y2),max(0,x1):max(0,x2)]
    return crop.size>0 and float(cv2.cvtColor(crop,cv2.COLOR_BGR2HSV)[...,1].mean())<COLORLESS


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
        'a brick floor or tiles','black adhesive tape on the floor','a hand','a shoe','a leaf',
        'a small cardboard box','a medicine box','an unknown object']

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


def phrase_result(logits,pred_boxes,tokens,shape,threshold=.28):
    """Cada caja recibe solo la descripción con mayor puntuación. La salida estándar de DINO junta
    todas las que superan el umbral («a crumpled paper a candy wrapper…») y el papel acababa como
    envoltura porque se buscaba «wrapper» primero."""
    import torch
    spans,current=[],[]
    for i,token in enumerate(tokens):
        if token in ('[CLS]','[SEP]','[PAD]'): continue
        if token=='.':
            if current: spans.append(current)
            current=[]
        else: current.append(i)
    if current: spans.append(current)
    names=[' '.join(tokens[i] for i in span).replace(' ##','') for span in spans]
    probs=logits.sigmoid()
    scores,best=torch.stack([probs[:,span].max(dim=1).values for span in spans],dim=1).max(dim=1)
    keep=scores>threshold
    h,w=shape[:2]
    cx,cy,bw,bh=pred_boxes[keep].unbind(-1)
    boxes=torch.stack([(cx-bw/2)*w,(cy-bh/2)*h,(cx+bw/2)*w,(cy+bh/2)*h],dim=-1)
    return {'boxes':boxes,'scores':scores[keep],'text_labels':[names[i] for i in best[keep].tolist()]}


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


def small_candidates(result, shape, min_side=10):
    h,w=shape[:2];found=[]
    for box,label,score in zip(result['boxes'],result['text_labels'],result['scores']):
        score=float(score);label=label.lower()
        kind=('envoltura' if ('wrapper' in label or 'snack bag' in label) else
              'papel / servilleta' if any(word in label for word in ('paper','tissue','napkin')) else
              'caja de carton' if 'cardboard' in label else
              'objeto por identificar' if ('cap' in label or 'roll' in label) else None)
        if kind is None or score < ({'envoltura':.28,'objeto por identificar':.35,'caja de carton':.35}.get(kind,.32)): continue
        b=np.asarray(box.cpu() if hasattr(box,'cpu') else box,float)
        if min(b[2:]-b[:2])<min_side or np.prod(b[2:]-b[:2])>w*h*.2: continue
        if kind in ('envoltura','objeto por identificar','caja de carton') and (b[0]<2 or b[1]<2 or b[2]>w-2 or b[3]>h-2): continue
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

    def find_robot(self,frame,min_side=10):
        inputs=self.processor(images=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB),text=ROBOT_PROMPT,
                              return_tensors='pt',size={'shortest_edge':512,'longest_edge':768})
        with self.torch.inference_mode(): outputs=self.model(**inputs)
        tokens=self.processor.tokenizer.convert_ids_to_tokens(inputs.input_ids[0])
        return robot_boxes(phrase_result(outputs.logits[0],outputs.pred_boxes[0],tokens,frame.shape),frame.shape,min_side)

    def detect(self,frame,turns=0,round_objects=False,min_side=10):
        view=np.rot90(frame,turns).copy()
        inputs=self.processor(images=cv2.cvtColor(view,cv2.COLOR_BGR2RGB),
            text=ROUND_PROMPT if round_objects else PROMPT,
            return_tensors='pt',size={'shortest_edge':512,'longest_edge':768})
        with self.torch.inference_mode(): outputs=self.model(**inputs)
        tokens=self.processor.tokenizer.convert_ids_to_tokens(inputs.input_ids[0])
        result=phrase_result(outputs.logits[0],outputs.pred_boxes[0],tokens,view.shape)
        verified=[]
        for box,name,score in small_candidates(result,view.shape,min_side):
            original=restore_box(box,frame.shape,turns)
            # Verificar antes de redondear/remapear conserva el mismo recorte en todos los giros.
            if name=='envoltura' and colorless(view,box):
                # Algo arrugado y sin color: se nombra papel si pasa cualquiera de las dos verificaciones
                # (CLIP suele ver la servilleta como envoltorio y la verificación de papel la rechaza).
                name='papel / servilleta'
                valid=self.verifier.check_wrapper(view,box)[0] or self.verifier.check(frame,original)[0]
            else:
                valid=(True if name in ('objeto por identificar','caja de carton') else
                       self.verifier.check_wrapper(view,box)[0] if name=='envoltura'
                       else self.verifier.check(frame,original)[0])
            if valid: verified.append((original,name,score))
        return verified


# Un objeto quieto y con el mismo aspecto se sigue mostrando entre reconocimientos hasta 20 s, en vez
# de desaparecer a los 4-6 s. La edad del reconocimiento se conserva: el conteo exige uno reciente.
STILL_LIMIT=20


def patch_of(frame, box):
    x1,y1,x2,y2=(int(v) for v in box)
    crop=frame[max(0,y1):max(0,y2),max(0,x1):max(0,x2)]
    if crop.size==0 or min(crop.shape[:2])<8:
        return None
    return cv2.resize(cv2.cvtColor(crop,cv2.COLOR_BGR2GRAY),(32,32),interpolation=cv2.INTER_AREA)


def same_look(reference, current, minimum=.6):
    """Textura parecida al recorte reconocido. Si el objeto se retira, el suelo ya no se le parece."""
    if reference is None or current is None or reference.std()<3 or current.std()<3:
        return False
    return float(cv2.matchTemplate(current,reference,cv2.TM_CCOEFF_NORMED)[0,0])>=minimum


def robot_boxes(result, shape, min_side=10):
    """Cajas descritas como robot, con confianza suficiente y un tamaño plausible."""
    h,w=shape[:2];found=[]
    for box,label,score in zip(result['boxes'],result['text_labels'],result['scores']):
        b=np.asarray(box.cpu() if hasattr(box,'cpu') else box,float);score=float(score)
        if 'robot' not in label or score<ROBOT_SCORE: continue
        if min(b[2:]-b[:2])<2*min_side or np.prod(b[2:]-b[:2])>.3*w*h: continue
        found.append((b,score))
    return sorted(found,key=lambda item:-item[1])


class PaperDetector:
    """Nombre conservado por compatibilidad; también reconoce envolturas, cajas y el robot."""
    def __init__(self,camera,focus=None):
        self.camera=camera
        self.focus=focus
        self.stop=threading.Event()
        self.latest=None
        self.status='Cargando papel y envolturas...'
        self.consumed=self.frame_stamp=None
        self.trackers=[]
        # El programa principal lo activa mientras no sigue al robot; resultado en coordenadas de análisis.
        self.want_robot=False
        self.robot=([],0)
        # Con un detector entrenado para los residuos de la escena, este (lento, en CPU) se puede apagar:
        # entonces solo busca el robot si se le pide.
        self.want_waste=True
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def run(self):
        try:
            with MODEL_LOCK:
                recognizer=SmallWasteRecognizer()
            history=[]
            search={False:[0,0],True:[0,0]};cycle=0
            last_stamp=None
            self.status='Papel y envolturas: buscando con varias orientaciones'
            while not self.stop.is_set():
                sample=detail_sample(self.camera)
                if sample is None or sample[2]==last_stamp:
                    self.stop.wait(.05);continue
                frame,full,stamp=sample;last_stamp=stamp
                # La imagen original (teléfono) da más detalle; las cajas vuelven a la de análisis.
                scale=full.shape[1]/frame.shape[1];min_side=10*scale
                if self.want_robot and (cycle%2==0 or not self.want_waste):
                    cycle+=1
                    self.robot=(to_work(recognizer.find_robot(full,min_side),scale),stamp,frame)
                    continue
                if not self.want_waste:
                    self.stop.wait(.2);continue
                # Escanear giros si falta la envoltura y conservar la orientación que funciona.
                region=self.focus.region(full.shape) if self.focus is not None else None
                # Con zoom se alterna recorte e imagen completa: lo que queda fuera del zoom también se
                # revisa (antes solo 1 de cada 4 análisis, y únicamente buscando objetos redondos).
                round_objects=cycle%4==3
                focused=region is not None and cycle%2==1 and not round_objects
                cycle+=1
                preferred,misses=search[focused]
                turns=(preferred+misses)%4
                if focused:
                    x1,y1,x2,y2=region
                    verified=restore_crop(recognizer.detect(full[y1:y2,x1:x2],turns,min_side=min_side),region,full.shape)
                else:
                    verified=recognizer.detect(full,0 if round_objects else turns,round_objects=round_objects,min_side=min_side)
                verified=to_work(verified,scale)
                if any(n=='envoltura' for _,n,_ in verified): preferred=turns;misses=0
                else: misses+=1
                if not round_objects: search[focused]=[preferred,misses]
                history=[(t,boxes) for t,boxes in history if stamp-t<12]
                confirmed=[]
                for box,name,score in verified:
                    limit=12 if name=='objeto por identificar' else 6
                    # Basta otro reconocimiento en el mismo sitio dentro del plazo, no en el análisis
                    # inmediatamente anterior: entre medias se gira la imagen o se buscan objetos redondos.
                    prior=[item for t,items in history if stamp-t<limit for item in items]
                    if any(oldname==name and overlap(box,oldbox)>.35 for oldbox,oldname,_ in prior):
                        confirmed.append((box,name,score))
                history.append((stamp,verified))
                self.latest=(confirmed,frame,stamp)
                self.status='Papel/envolturas/cajas + objetos por identificar'
                self.stop.wait(.1)
        except Exception as exc:
            self.status='Papel/envolturas no disponible: '+str(exc)

    @staticmethod
    def lifetime(name): return {'objeto por identificar':8}.get(name,6)

    def read(self,frame,stamp):
        result=self.latest
        if result is not None and result[2]!=self.consumed:
            boxes,source,source_stamp=result;self.consumed=source_stamp
            # Un análisis sin resultados no borra instantáneamente un seguimiento aún reciente.
            for box,name,score in boxes:
                if not 0 <= stamp-source_stamp < self.lifetime(name): continue
                if name=='objeto por identificar' and any(t[5]!='objeto por identificar' and
                        stamp-t[2]<self.lifetime(t[5]) and overlap(t[4],box)>.35 for t in self.trackers):
                    continue
                self.trackers=[t for t in self.trackers if overlap(t[4],box)<.35]
                x1,y1,x2,y2=box.astype(int)
                tracker=cv2.TrackerCSRT_create()
                tracker.init(source,(x1,y1,x2-x1,y2-y1))
                anchor=(patch_of(source,box),np.asarray(box,float))
                self.trackers.append((tracker,score,source_stamp,(x2-x1)*(y2-y1),box,name,anchor))
        if stamp!=self.frame_stamp:
            self.frame_stamp=stamp;retained=[]
            for tracker,score,observed,area,oldbox,name,anchor in self.trackers:
                age=stamp-observed
                if not 0 <= age < max(self.lifetime(name),STILL_LIMIT if anchor else 0): continue
                ok,(x,y,w,h)=tracker.update(frame)
                box=np.array([x,y,x+w,y+h])
                followed=ok and .6*area < w*h < 1.6*area and x>=0 and y>=0 and x+w<frame.shape[1] and y+h<frame.shape[0]
                if age>=self.lifetime(name) or not followed:
                    # Objeto quieto: se comprueba en el sitio donde se reconoció, porque el seguimiento
                    # resbala sobre objetos sin textura (servilleta blanca sobre suelo claro).
                    if not (anchor and same_look(anchor[0],patch_of(frame,anchor[1]))):
                        continue
                    box=anchor[1].copy()
                retained.append((tracker,score,observed,area,box,name,anchor))
            self.trackers=retained
        return [(b.astype(int).tolist(),name,s,stamp-t) for _,s,t,_,b,name,_ in self.trackers]
