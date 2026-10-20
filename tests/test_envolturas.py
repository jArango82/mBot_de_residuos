"""Geometría, asociación y caducidad del reconocimiento de envolturas."""
from pathlib import Path
import sys,unittest,tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import numpy as np
from vision_papel import restore_box,small_candidates,PaperDetector
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
        detector.trackers=[(Tracker(),.4,0.,400,np.array([10,10,30,30]),'envoltura')]
        self.assertEqual(len(detector.read(frame,2)),1)
        self.assertEqual(detector.read(frame,6.1),[])
    def test_delayed_wrapper_recognition_still_records_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            store=EventStore(Path(temp)/'db.sqlite');counter=SeparationCounter(store)
            polygon=np.float32([[100,100],[300,100],[300,300],[100,300]])
            for stamp,x in [(2,250),(3,250),(4,280),(5,310),(6,310)]:
                counter.update([{'box':[x,150,x+20,170],'label':'envoltura','confidence':.4,'observation_age':1.8}],polygon,True,stamp)
            self.assertEqual(store.report()['total'],1)
if __name__=='__main__':unittest.main()
