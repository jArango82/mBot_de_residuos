"""Selección de cámara externa (LifeCam, Samsung, Camo) e imagen de análisis, sin webcam."""
from pathlib import Path
import sys, threading, time, unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import argparse
import cv2
import numpy as np
from camaras_mac import BUILTIN_TRANSPORT, camera_arg, opencv_devices, select_external, size_arg
from vision_ranger import Camera, black_bars, capture_size, work_size
from vision_zoom import InspectionZoom, restore_crop, to_work
from vision_linea_robot import frozen_while_moving
from vision_residuos import outside_zone
from camaras_mac import WATERMARKS


class Device:
    def __init__(self, name, uid, kind=None, transport=None):
        self.name, self.uid, self.kind, self.transport = name, uid, kind, transport
    def localizedName(self): return self.name
    def uniqueID(self): return self.uid


class TypedDevice(Device):
    def deviceType(self): return self.kind
    def transportType(self): return self.transport


MAC=Device('Camara MacBook Air','6C707041-05AC-0011')
MAC_TYPED=TypedDevice('Camara integrada','BUILTIN-1','AVCaptureDeviceTypeBuiltInWideAngleCamera',BUILTIN_TRANSPORT)
MAC_TRANSPORT=TypedDevice('Camara sin tipo','BUILTIN-2','AVCaptureDeviceTypeExternal',BUILTIN_TRANSPORT)
USB=Device('Microsoft LifeCam VX-5000','0x1120000045e0728')
GALAXY=TypedDevice('Galaxy S24 Ultra','SAMSUNG-1','AVCaptureDeviceTypeExternal',1)
CAMO=TypedDevice('Camo','CAMO-1','AVCaptureDeviceTypeExternal',2)
OTHER=TypedDevice('Webcam generica','OTHER-1','AVCaptureDeviceTypeExternal',1)


class SelectionTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='darwin','NSString solo existe en macOS')
    def test_system_order_is_not_opencv_order(self):
        class AV:
            AVMediaTypeVideo='video'
            AVMediaTypeMuxed='muxed'
            class AVCaptureDevice:
                @staticmethod
                def devicesWithMediaType_(kind):
                    return [MAC,USB] if kind=='video' else []
        cameras=opencv_devices(AV)
        self.assertEqual(select_external(devices=cameras),(0,USB.name,USB.uid))
        self.assertEqual(cameras[1].uid,MAC.uid)

    def test_samsung_or_camo_selected_automatically(self):
        self.assertEqual(select_external(devices=[MAC_TYPED,GALAXY])[1],GALAXY.name)
        self.assertEqual(select_external(devices=[CAMO,MAC])[1],CAMO.name)

    def test_missing_external_never_falls_back(self):
        for devices in ([MAC],[MAC_TYPED],[MAC_TRANSPORT],[]):
            with self.assertRaisesRegex(RuntimeError,'No se abrira la camara del Mac'):
                select_external(devices=devices)

    def test_builtin_rejected_by_index_and_name(self):
        for devices in ([USB,MAC],[USB,MAC_TYPED],[USB,MAC_TRANSPORT]):
            with self.assertRaises(RuntimeError): select_external(1,devices)
        with self.assertRaises(RuntimeError): select_external('macbook',[MAC,GALAXY])
        with self.assertRaises(RuntimeError): select_external('integrada',[MAC_TYPED,GALAXY])

    def test_two_known_cameras_do_not_guess(self):
        for devices in ([USB,USB,MAC],[USB,GALAXY],[GALAXY,CAMO]):
            with self.assertRaisesRegex(RuntimeError,'varias'): select_external(devices=devices)
        self.assertEqual(select_external('galaxy',[USB,GALAXY])[0],1)
        self.assertEqual(select_external('samsung',[USB,GALAXY])[0],1)
        self.assertEqual(select_external('camo',[GALAXY,CAMO])[0],1)
        self.assertEqual(select_external('LIFECAM',[USB,GALAXY])[0],0)

    def test_unknown_external_needs_explicit_choice(self):
        with self.assertRaisesRegex(RuntimeError,'Webcam generica'): select_external(devices=[OTHER,MAC])
        self.assertEqual(select_external('generica',[MAC,OTHER])[0],1)
        self.assertEqual(select_external(1,[MAC,OTHER])[0],1)

    def test_invalid_indices_and_arguments_fail(self):
        for index in (-1,2):
            with self.assertRaises(RuntimeError): select_external(index,[USB,MAC])
        self.assertEqual(camera_arg('2'),2)
        self.assertEqual(camera_arg('samsung'),'samsung')
        self.assertEqual(size_arg('1920x1080'),(1920,1080))
        for text in ('1920',' x ','10x10'):
            with self.assertRaises(argparse.ArgumentTypeError): size_arg(text)


class FrameTests(unittest.TestCase):
    def test_capture_keeps_lifecam_and_phone_proportion(self):
        self.assertEqual(capture_size('LifeCam',(640,480)),(640,480))
        self.assertEqual(capture_size('Samsung',(1920,1080)),(1280,720))
        self.assertEqual(capture_size('Camo',(1080,1920)),(720,1280))
        self.assertEqual(capture_size('Samsung',(1280,960)),(1280,960))
        self.assertEqual(capture_size('Samsung',None),(1280,720))
        self.assertEqual(capture_size('Samsung',(1920,1080),(1920,1080)),(1920,1080))

    def test_analysis_frame_keeps_640_geometry(self):
        self.assertEqual(work_size(640,480),(640,480))
        self.assertEqual(work_size(1280,720),(640,360))
        self.assertEqual(work_size(1920,1080),(640,360))
        self.assertEqual(work_size(720,1280),(360,640))

    def test_black_bands_are_reported(self):
        self.assertFalse(black_bars(np.zeros((480,640,3),np.uint8)))
        frame=np.full((480,640,3),120,np.uint8)
        self.assertFalse(black_bars(frame))
        frame[:60]=0;frame[-60:]=0
        self.assertTrue(black_bars(frame))

    def make_camera(self,frames,size=(1280,720)):
        class Capture:
            def __init__(self):self.items=list(frames)
            def read(self):
                if not self.items:
                    camera.stop.set();return False,None
                return True,self.items.pop(0)
            def release(self):pass
        camera=Camera.__new__(Camera)
        camera.name='Galaxy S24 Ultra';camera.capture=Capture()
        camera.size=size;camera.work_size=work_size(*size);camera.scale=size[0]/camera.work_size[0]
        camera.latest=camera.full=None;camera.previous=np.zeros((size[1],size[0],3),np.uint8)
        camera.changed=0.;camera.fps=0.;camera.started=0.;camera.bars_checked=True;camera.lock=threading.Lock();camera.stop=threading.Event()
        return camera

    def test_phone_frame_is_reduced_and_original_kept(self):
        full=np.random.default_rng(1).integers(0,255,(720,1280,3),np.uint8)
        camera=self.make_camera([full])
        camera.run()
        frame,original,stamp=camera.read_detail()
        self.assertEqual(frame.shape,(360,640,3))
        self.assertIs(original,full)
        self.assertEqual(camera.read()[1],stamp)
        self.assertIn('1280x720>640x360',camera.summary())

    def test_repeated_frame_is_not_a_change(self):
        rng=np.random.default_rng(2)
        first=rng.integers(0,255,(720,1280,3),np.uint8)
        camera=self.make_camera([first])
        camera.run();changed=camera.changed
        self.assertGreater(changed,0)
        camera.stop.clear();camera.capture.items=[first.copy(),first.copy()]
        camera.run()
        self.assertEqual(camera.changed,changed)
        camera.stop.clear();camera.capture.items=[rng.integers(0,255,(720,1280,3),np.uint8)]
        camera.run()
        self.assertGreater(camera.changed,changed)

    def test_frozen_image_stops_only_during_motion(self):
        self.assertFalse(frozen_while_moving(None,0,10))
        self.assertFalse(frozen_while_moving(9.7,0,10))
        self.assertFalse(frozen_while_moving(9,9.8,10))
        self.assertTrue(frozen_while_moving(9,9.2,10))


class DetailTests(unittest.TestCase):
    def test_zoom_uses_real_pixels_and_keeps_annotations(self):
        rng=np.random.default_rng(3)
        detail=rng.integers(0,255,(720,1280,3),np.uint8)
        plain=cv2.resize(detail,(640,360),interpolation=cv2.INTER_AREA)
        view=plain.copy()
        cv2.rectangle(view,(300,170),(340,190),(0,255,0),2)
        zoom=InspectionZoom(2)
        rendered=zoom.render(view,detail,plain)[:360]
        x1,y1,x2,y2=zoom.region(detail.shape)
        self.assertEqual((x1,y1,x2,y2),(320,180,960,540))
        np.testing.assert_array_equal(rendered[10,10],detail[y1+10,x1+10])
        np.testing.assert_array_equal(rendered[(170-90)*2,(300-160)*2+5],[0,255,0])
        self.assertEqual(zoom.display[2],(160,90,480,270))

    def test_crop_boxes_return_to_analysis_coordinates(self):
        items=[(np.array([20,30,60,80]),'botella',.8)]
        restored=restore_crop(items,(320,180,960,540),(720,1280,3))
        np.testing.assert_array_equal(restored[0][0],[340,210,380,260])
        np.testing.assert_array_equal(to_work(restored,2)[0][0],[170,105,190,130])
        self.assertIs(to_work(items,1)[0][0],items[0][0])


class WatermarkTests(unittest.TestCase):
    def test_camo_watermark_is_ignored_but_nearby_waste_is_kept(self):
        zone=WATERMARKS['Camo']
        watermark=([564,287,619,344],'objeto por identificar',.52,0)  # caja real de la prueba con Camo
        bottle=([500,250,580,330],'botella',.8,0)                      # toca la zona, la mayor parte fuera
        centre=([300,150,340,200],'lata',.7,0)
        kept=outside_zone([watermark,bottle,centre],zone,(360,640,3))
        self.assertEqual([k[1] for k in kept],['botella','lata'])
        self.assertEqual(len(outside_zone([watermark],None,(360,640,3))),1)
        self.assertEqual(outside_zone([([1128,574,1238,688],'envoltura',.4)],zone,(720,1280,3)),[])


class PortTests(unittest.TestCase):
    def test_samsung_phone_is_never_probed_as_ranger(self):
        from actualizar_ranger import candidates
        class Port:
            def __init__(self,device,vid):self.device,self.vid=device,vid
        ports=[Port('/dev/cu.usbmodem-galaxy',0x04E8),Port('/dev/cu.wchusbserial1',0x1A86),Port('/dev/cu.Bluetooth',None)]
        with patch('serial.tools.list_ports.comports',return_value=ports):
            self.assertEqual(candidates(),['/dev/cu.wchusbserial1'])


if __name__=='__main__':unittest.main(verbosity=2)
