"""El zoom conserva coordenadas de conteo y no acepta objetos cortados."""
from pathlib import Path
import sys, unittest, tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import cv2
import numpy as np
from vision_zoom import InspectionZoom, restore_crop
from vision_superres import SuperResolution
from vision_residuos import merge_observations, category
from conteo_residuos import EventStore, SeparationCounter


class ZoomTests(unittest.TestCase):
    def test_zoom_click_and_reset_keep_full_frame_coordinates(self):
        frame=np.zeros((480,640,3),np.uint8)
        zoom=InspectionZoom(2)
        np.testing.assert_array_equal(zoom.region(frame.shape),(160,120,480,360))
        original=frame.copy()
        rendered=zoom.render(frame)
        self.assertEqual(rendered.shape,(520,640,3))
        np.testing.assert_array_equal(frame,original)
        zoom.mouse(cv2.EVENT_LBUTTONDOWN,480,240,0,None)
        self.assertEqual(zoom.region(frame.shape),(240,120,560,360))
        zoom.key(ord('0'))
        self.assertIsNone(zoom.region(frame.shape))

    def test_minimap_moves_center_and_clamps_to_image(self):
        frame=np.zeros((480,640,3),np.uint8)
        zoom=InspectionZoom(4)
        zoom.render(frame)
        x,y,_,_=zoom.display[3]
        zoom.mouse(cv2.EVENT_LBUTTONDOWN,x,y,0,None)
        self.assertEqual(zoom.region(frame.shape),(0,0,160,120))
        zoom.adjust(100)
        self.assertEqual(zoom.level,4)
        zoom.adjust(-100)
        self.assertEqual(zoom.level,1)

    def test_cropped_detections_remap_and_merge_without_duplicates(self):
        items=[(np.array([20,30,50,70]),'botella',.8),
               (np.array([0,30,50,70]),'envoltura',.8),
               (np.array([290,30,320,70]),'lata',.8)]
        mapped=restore_crop(items,(160,120,480,360),(480,640,3))
        self.assertEqual(len(mapped),1)
        np.testing.assert_array_equal(mapped[0][0],[180,150,210,190])
        merged=merge_observations([([181,151,211,191],'botella',.7)],mapped)
        self.assertEqual(len(merged),1)

    def test_ai_toggle_keeps_source_and_returns_to_original(self):
        class Model:
            def upsample(self, image):
                return cv2.resize(image,None,fx=2,fy=2)
        enhancer=SuperResolution()
        enhancer.model=Model()
        zoom=InspectionZoom(enhancer=enhancer)
        zoom.key(ord('i'))
        self.assertEqual(zoom.level,2)
        self.assertTrue(enhancer.enabled)
        frame=np.zeros((480,640,3),np.uint8)
        zoom.render(frame)
        self.assertEqual(frame.sum(),0)
        self.assertIn('IA x2',enhancer.status)
        zoom.key(ord('0'))
        self.assertFalse(enhancer.enabled)
        self.assertIsNone(zoom.region(frame.shape))

    def test_missing_ai_model_falls_back_without_breaking_camera(self):
        with tempfile.TemporaryDirectory() as folder:
            enhancer=SuperResolution(True,Path(folder)/'missing.pb')
            frame=np.zeros((30,40,3),np.uint8)
            self.assertIs(enhancer.enhance(frame),frame)
            self.assertFalse(enhancer.enabled)
            self.assertIn('Falta modelo',enhancer.status)

    def test_ambiguous_object_is_never_counted_as_waste(self):
        self.assertEqual(category('tapa de botella'),'objeto por identificar')
        with tempfile.TemporaryDirectory() as temp:
            store=EventStore(Path(temp)/'db.sqlite')
            counter=SeparationCounter(store)
            area=np.float32([[100,100],[300,100],[300,300],[100,300]])
            for stamp,x in [(1,250),(2,250),(3,310),(4,310)]:
                counter.update([{'label':'objeto por identificar','confidence':.8,'box':[x,150,x+20,170],
                                 'countable':False,'observation_age':0}],area,True,stamp)
            self.assertEqual(store.report()['total'],0)

if __name__=='__main__':unittest.main()
