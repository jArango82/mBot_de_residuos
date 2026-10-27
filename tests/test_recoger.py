"""Recogida de imágenes para entrenar: numeración, intervalo y rechazo de imágenes inútiles."""
from pathlib import Path
import sys, tempfile, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import cv2
import numpy as np
from recoger_imagenes import Recorder


class RecorderTests(unittest.TestCase):
    def test_numbering_continues_an_existing_session(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'sesion'
            folder.mkdir()
            (folder/'0007.jpg').write_bytes(b'')
            recorder=Recorder(folder)
            frame=np.full((72,128,3),120,np.uint8)
            path=recorder.save(frame,10)
            self.assertEqual(path.name,'0008.jpg')
            self.assertEqual(cv2.imread(str(path)).shape,(72,128,3))
            self.assertEqual(recorder.saved,1)

    def test_automatic_photo_waits_for_interval(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder=Recorder(Path(temp)/'s',auto=True,every=2)
            self.assertTrue(recorder.due(0))
            recorder.save(np.full((10,10,3),120,np.uint8),5)
            self.assertFalse(recorder.due(6.5))
            self.assertTrue(recorder.due(7))
            recorder.auto=False
            self.assertFalse(recorder.due(100))

    def test_black_frozen_or_missing_images_are_not_saved(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder=Recorder(Path(temp)/'s')
            good=np.full((10,10,3),120,np.uint8)
            self.assertIsNone(recorder.problem(good,.1))
            self.assertIn('negra',recorder.problem(np.zeros((10,10,3),np.uint8),.1))
            self.assertIn('congelada',recorder.problem(good,3))
            self.assertIn('Sin imagen',recorder.problem(None,0))

    def test_blurred_photo_is_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            recorder=Recorder(Path(temp)/'s')
            sharp=np.zeros((720,1280,3),np.uint8)
            sharp[::16]=255;sharp[:,::16]=255                      # textura fina, como las vetas del suelo
            self.assertFalse(recorder.blurry(sharp))
            self.assertTrue(recorder.blurry(cv2.GaussianBlur(sharp,(0,0),8)))
            self.assertFalse(Recorder(Path(temp)/'t',sharpness=0).blurry(cv2.GaussianBlur(sharp,(0,0),8)))


if __name__=='__main__':unittest.main()
