"""Estabilidad de detecciones: histéresis, voto de etiqueta y prioridad frente a objetos ambiguos."""
from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
from vision_residuos import AMBIGUOUS, StableObjects, merge_observations, small_enough

BOX=[100,100,140,180]


class StabilityTests(unittest.TestCase):
    def test_followed_object_survives_weak_scores_but_new_weak_one_is_ignored(self):
        tracker=StableObjects()
        tracker.update([(BOX,'botella',.5)],0)
        self.assertEqual(len(tracker.update([(BOX,'botella',.5)],.2)),1)
        for t in (.4,.6,.8,1.0):
            # Puntuación bajo el umbral de creación: mantiene el objeto ya seguido.
            self.assertEqual([d[1] for d in tracker.update([(BOX,'botella',.18),([400,50,440,90],'lata',.18)],t)],['botella'])
        self.assertEqual(tracker.update([],1.8),[])

    def test_one_odd_label_does_not_rename_object(self):
        tracker=StableObjects()
        for t in (0,.2,.4):
            tracker.update([(BOX,'botella',.6)],t)
        self.assertEqual(tracker.update([([101,100,141,181],'vaso plastico',.35)],.6)[0][1],'botella')
        for t in (.8,1.0,1.2,1.4,1.6,1.8):
            names=[d[1] for d in tracker.update([(BOX,'vaso plastico',.6)],t)]
        self.assertEqual(names,['vaso plastico'])  # Un cambio sostenido sí se acepta.

    def test_neighbour_with_other_label_stays_separate(self):
        tracker=StableObjects()
        for t in (0,.2):
            found=tracker.update([(BOX,'botella',.6),([125,100,165,180],'lata',.6)],t)
        self.assertEqual(sorted(d[1] for d in found),['botella','lata'])

    def test_custom_model_needs_higher_score_and_small_boxes(self):
        strict=StableObjects(new_conf=.6)
        for t in (0,.2): found=strict.update([(BOX,'caja de carton',.53)],t)
        self.assertEqual(found,[])                                   # como las falsas medidas (0,26-0,53)
        for t in (.4,.6): found=strict.update([(BOX,'caja de carton',.7)],t)
        self.assertEqual([f[1] for f in found],['caja de carton'])
        shape=(1080,1920,3)
        boxes=[([0,0,960,540],'caja de carton',.9),([100,100,300,250],'caja de carton',.9)]
        self.assertEqual([b[0] for b in small_enough(boxes,shape)],[[100,100,300,250]])

    def test_ambiguous_proposal_does_not_hide_concrete_detection(self):
        bottle=(BOX,'botella',.56,0)
        ambiguous=([98,99,142,182],AMBIGUOUS,.57,1)
        self.assertEqual([m[1] for m in merge_observations([bottle],[ambiguous])],['botella'])
        self.assertEqual([m[1] for m in merge_observations([],[ambiguous])],[AMBIGUOUS])
        paper=([98,99,142,182],'papel / servilleta',.4,1)
        self.assertEqual([m[1] for m in merge_observations([bottle],[paper])],['papel / servilleta'])


class TrainedOnlyTests(unittest.TestCase):
    """Con el detector entrenado con caja y lata, el general (YOLO-World) no se ejecuta; con el primero, sí."""
    def run_detector(self, names, generic):
        import threading, time
        import numpy as np
        from unittest.mock import patch
        import vision_ranger
        calls = []
        class Tensor(np.ndarray):
            def cpu(self): return self
            def numpy(self): return np.asarray(self)
        class Box:
            def __init__(self, cls):
                self.xyxy = [np.array([10., 10., 40., 40.]).view(Tensor)]; self.cls = np.array(cls); self.conf = np.array(.9)
        class Result:
            def __init__(self, boxes): self.boxes = boxes
        class Model:
            def __init__(self, path):
                self.path = path
                self.names = {0: 'bottle'} if 'world' in str(path) else dict(enumerate(names))
                self.ckpt = {'train_args': {'imgsz': 800}}
            def predict(self, image, **k):
                calls.append(self.path)
                return [Result([Box(0)] if image.sum() else [])]
        class Camera:
            work_shape = (360, 640, 3)
            def latest(self): return np.ones((360, 640, 3), np.uint8), time.monotonic()
        with patch('ultralytics.YOLO', Model), patch.object(vision_ranger.Path, 'is_file', return_value=True), \
             patch('vision_zoom.detail_sample', lambda cam: (np.ones((360, 640, 3), np.uint8), np.ones((720, 1280, 3), np.uint8), time.monotonic())):
            detector = vision_ranger.WasteDetector(Camera(), 'world.pt', None, custom='propio.pt', generic=generic)
            time.sleep(.6); detector.stop.set(); detector.thread.join(2)
        return detector, [c for c in calls]

    def test_can_model_turns_generic_off(self):
        detector, calls = self.run_detector(['caja de carton', 'lata'], None)
        self.assertIs(detector.generic, False)
        self.assertIn('solo residuos entrenados', detector.status)
        self.assertEqual(calls.count('world.pt'), 1)          # solo la inferencia de calentamiento

    def test_first_model_or_flag_keeps_generic(self):
        detector, calls = self.run_detector(['caja de carton', 'envoltura', 'papel / servilleta'], None)
        self.assertIs(detector.generic, True)
        self.assertGreater(calls.count('world.pt'), 1)
        detector, calls = self.run_detector(['caja de carton', 'lata'], True)   # --otros-residuos
        self.assertGreater(calls.count('world.pt'), 1)


class SheetConfidenceTests(unittest.TestCase):
    def test_can_on_its_sheet_needs_less_confidence(self):
        import numpy as np
        from vision_ranger import on_own_sheet
        zones={'lata':np.float32([[100,100],[160,100],[160,160],[100,160]])}
        self.assertEqual(on_own_sheet([120,120,140,140],'lata',.25,zones),.5)       # encima de su hoja
        self.assertEqual(on_own_sheet([300,300,320,320],'lata',.25,zones),.25)      # lejos: igual
        self.assertEqual(on_own_sheet([120,120,140,140],'caja de carton',.25,zones),.25)   # no es su hoja
        self.assertEqual(on_own_sheet([120,120,140,140],'lata',.1,zones),.1)        # demasiado poca


class CautionTests(unittest.TestCase):
    """Cinco residuos (1/11): las botellas entrenadas conservan su nombre y, ante la duda entre botella de plástico
    y envase de blanqueador, gana el peligroso."""
    def test_trained_bottles_keep_their_names(self):
        from vision_residuos import category
        self.assertEqual(category('botella de vidrio'),'botella de vidrio')
        self.assertEqual(category('botella de plastico'),'botella de plastico')
        self.assertEqual(category('botella de agua'),'botella')     # descripciones generales: como antes

    def test_same_object_with_two_labels_becomes_one(self):
        from vision_residuos import one_label
        far=[300,300,340,380]
        found=one_label([(BOX,'botella de plastico',.45),(BOX,'envase de blanqueador',.3),(far,'lata',.6)])
        self.assertEqual(sorted((n,c) for _,n,c in found),[('envase de blanqueador',.45),('lata',.6)])
        found=one_label([(BOX,'caja de carton',.7),(BOX,'lata',.3)])
        self.assertEqual([(n,c) for _,n,c in found],[('caja de carton',.7)])     # sin pareja peligrosa: la más segura
        found=one_label([(BOX,'envase de blanqueador',.6),(BOX,'botella de plastico',.4)])
        self.assertEqual([(n,c) for _,n,c in found],[('envase de blanqueador',.6)])

    def test_doubtful_bottle_is_treated_as_dangerous(self):
        tracker=StableObjects()
        tracker.update([(BOX,'botella de plastico',.7)],0)
        names=[d[1] for d in tracker.update([(BOX,'botella de plastico',.7)],.2)]
        self.assertEqual(names,['botella de plastico'])
        for t in (.4,.6):
            names=[d[1] for d in tracker.update([(BOX,'envase de blanqueador',.6)],t)]
        self.assertEqual(names,['envase de blanqueador'])
        other=StableObjects()        # una sola duda débil no basta
        for t in (0,.2,.4,.6):
            other.update([(BOX,'botella de plastico',.7)],t)
        self.assertEqual([d[1] for d in other.update([(BOX,'envase de blanqueador',.3)],.8)],['botella de plastico'])


if __name__=='__main__':unittest.main()
