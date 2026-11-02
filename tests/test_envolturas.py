"""Geometría, asociación y caducidad del reconocimiento de envolturas."""
from pathlib import Path
import sys,unittest,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import numpy as np
from vision_papel import restore_box,small_candidates,PaperDetector,phrase_result,colorless,robot_boxes
from vision_residuos import merge_observations
from conteo_residuos import EventStore,SeparationCounter

class WrapperTests(unittest.TestCase):
    def test_boxes_return_to_original_for_every_rotation(self):
        # Caja original (40,70)-(90,110) en imagen 640x480; coordenadas continuas.
        rotated=[[40,70,90,110],[70,550,110,600],[550,370,600,410],[370,40,410,90]]
        for k,b in enumerate(rotated):
            np.testing.assert_allclose(restore_box(b,(480,640,3),k),[40,70,90,110])
    def test_candidates_reject_floor_unknown_edges_and_duplicates(self):
        result={'boxes':np.array([[100,100,130,125],[101,101,131,126],[0,0,640,480],[0,20,40,60],[300,300,330,320]]),
                'text_labels':['a candy wrapper','a plastic wrapper','a wrapper','a snack bag','a chair'],
                'scores':[.4,.3,.8,.5,.9]}
        found=small_candidates(result,(480,640,3))
        self.assertEqual(len(found),1);self.assertEqual(found[0][1],'envoltura')
    def test_each_box_keeps_only_its_best_description(self):
        import torch
        tokens=['[CLS]','a','crumpled','paper','.','a','candy','wrap','##per','.','a','bottle','.','[SEP]']
        logit=lambda p:float(torch.logit(torch.tensor(p)))
        logits=torch.full((3,len(tokens)),-9.)
        logits[0,1:4]=logit(.39);logits[0,5:9]=logit(.31)   # papel arrugado: también parece envoltura
        logits[1,10:12]=logit(.42)                          # botella
        logits[2,5:9]=logit(.2)                             # bajo el umbral
        boxes=torch.tensor([[.5,.5,.1,.2],[.25,.25,.1,.1],[.8,.8,.1,.1]])
        result=phrase_result(logits,boxes,tokens,(480,640,3))
        self.assertEqual(result['text_labels'],['a crumpled paper','a bottle'])
        np.testing.assert_allclose(result['boxes'][0].numpy(),[288,192,352,288],atol=1e-3)
        found=small_candidates(result,(480,640,3))
        self.assertEqual([f[1] for f in found],['papel / servilleta'])  # antes ganaba «envoltura»
    def test_colorless_crumpled_object_is_checked_as_paper(self):
        import cv2
        image=np.full((100,200,3),200,np.uint8)
        image[20:80,110:190]=cv2.cvtColor(np.uint8([[[60,110,170]]]),cv2.COLOR_HSV2BGR)  # verde como la envoltura real
        self.assertTrue(colorless(image,[20,20,90,80]))      # servilleta blanca
        self.assertFalse(colorless(image,[110,20,190,80]))   # envoltura de color
        self.assertFalse(colorless(image,[300,20,390,80]))   # fuera de la imagen: no decide
    def test_robot_needs_its_description_confidence_and_plausible_size(self):
        result={'boxes':np.array([[300,150,360,210],[400,150,460,210],[0,0,1800,1000],[100,100,160,160]],float),
                'text_labels':['a small robot car with tracks','a small robot car with tracks','a small robot car with tracks','a shoe'],
                'scores':[.72,.40,.80,.90]}
        found=robot_boxes(result,(1080,1920,3),min_side=20)
        self.assertEqual([b.tolist() for b,_ in found],[[300,150,360,210]])
    def test_general_and_specialist_do_not_double_count_one_object(self):
        general=[([100,100,130,125],'envoltura plastica',.5,.2),([200,200,230,250],'botella',.8,.1)]
        special=[([101,101,130,124],'envoltura',.4,1.5)]
        merged=merge_observations(general,special)
        self.assertEqual(len(merged),2);self.assertEqual([x[1] for x in merged],['botella','envoltura'])
    def test_tracker_survives_one_missing_result_but_expires(self):
        class Tracker:
            def update(self,frame):return True,(10,10,20,20)
        detector=PaperDetector.__new__(PaperDetector)
        frame=np.zeros((100,100,3),np.uint8)
        detector.latest=([],frame,1.0);detector.consumed=None;detector.frame_stamp=None
        detector.trackers=[(Tracker(),.4,0.,400,np.array([10,10,30,30]),'envoltura',None)]
        self.assertEqual(len(detector.read(frame,2)),1)
        self.assertEqual(detector.read(frame,6.1),[])
    def test_still_object_stays_until_it_is_removed(self):
        import cv2
        from vision_papel import patch_of
        class Tracker:
            def update(self,frame):return True,(40,40,40,30)
        rng=np.random.default_rng(4)
        scene=np.full((200,200,3),200,np.uint8)
        scene[40:70,40:80]=rng.integers(0,255,(30,40,3),np.uint8)       # caja con textura propia
        box=np.array([40,40,80,70])
        detector=PaperDetector.__new__(PaperDetector)
        detector.latest=([],scene,1.0);detector.consumed=1.0;detector.frame_stamp=None
        detector.trackers=[(Tracker(),.5,0.,1200,box,'caja de carton',(patch_of(scene,box),box.astype(float)))]
        self.assertEqual(len(detector.read(scene,15)),1)                 # quieta: sigue tras 6 s
        self.assertGreater(detector.read(scene,15.2)[0][3],6)            # la edad del reconocimiento se conserva
        removed=scene.copy();removed[40:70,40:80]=200;cv2.line(removed,(40,45),(80,65),(150,150,150),2)
        self.assertEqual(detector.read(removed,15.4),[])                 # retirada: el suelo no se parece
        detector.trackers=[(Tracker(),.5,0.,1200,box,'caja de carton',(patch_of(scene,box),box.astype(float)))]
        self.assertEqual(detector.read(scene,25),[])                     # nunca más de 20 s sin reconocerla
    def test_delayed_wrapper_recognition_still_records_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EventStore(Path(temp)/'db.sqlite');counter=SeparationCounter(store)
            polygon=np.float32([[100,100],[300,100],[300,300],[100,300]])
            for stamp,x in [(2,250),(3,250),(4,280),(5,310),(6,310)]:
                counter.update([{'box':[x,150,x+20,170],'label':'envoltura','confidence':.4,'observation_age':1.8}],polygon,True,stamp)
            self.assertEqual(store.report()['total'],1)
if __name__=='__main__':unittest.main()
