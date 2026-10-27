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


if __name__=='__main__':unittest.main()
