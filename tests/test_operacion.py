"""Pruebas reproducibles sin cámara, robot ni modelos grandes."""
from pathlib import Path
import asyncio
import json
import sys
import tempfile
import time
import unittest
from unittest.mock import patch, AsyncMock
from urllib.request import urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import numpy as np
from conteo_residuos import EventStore, SeparationCounter
from vision_linea_robot import assess_line, assess_rectangle
from vision_ranger import CommandState, BluetoothGuard
from ranger_bluetooth import RangerBluetooth
from actualizar_ranger import VERSION, update, update_if_present
from dashboard import serve

AREA=np.float32([[100,100],[300,100],[300,300],[100,300]])
def obj(x,y=150,age=0,label='botella'):
    return dict(box=[x,y,x+20,y+20],label=label,confidence=.8,observation_age=age)

class CounterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=EventStore(Path(self.tmp.name)/'data.db');self.c=SeparationCounter(self.store)
    def tearDown(self): self.tmp.cleanup()
    def feed(self,x,t,**kw):return self.c.update([obj(x,**kw)],AREA,True,t)
    def total(self):return self.store.report()['total']
    def inside(self):self.feed(250,0);self.feed(250,.5)
    def exit(self):self.feed(280,1);self.feed(310,1.5);self.feed(310,2)
    def test_empty_history_has_zero_elapsed_time(self):
        self.assertEqual(self.store.report("nonexistent")["elapsed"],0)
    def test_confirmed_exit_once(self):
        self.inside();self.exit();self.feed(315,2.5);self.assertEqual(self.total(),1)
    def test_already_outside_not_counted(self):
        self.feed(320,0);self.feed(320,.5);self.assertEqual(self.total(),0)
    def test_disappearance_is_not_exit(self):
        self.inside();self.c.update([],AREA,True,1);self.c.update([],AREA,True,8);self.assertEqual(self.total(),0)
    def test_one_frame_outside_not_enough(self):
        self.inside();self.feed(310,1);self.assertEqual(self.total(),0)
    def test_partial_box_outside_does_not_count(self):
        self.inside();self.feed(290,1);self.feed(290,1.5);self.assertEqual(self.total(),0)
    def test_same_detection_repeated_does_not_confirm(self):
        self.feed(250,0);self.feed(250,.5,age=.5);self.feed(310,1);self.feed(310,1.5);self.assertEqual(self.total(),0)
    def test_lost_border_invalidates_transition(self):
        self.inside();self.c.update([],None,False,1);self.exit();self.assertEqual(self.total(),0)
    def test_relocated_border_does_not_create_exit(self):
        self.inside();self.c.update([obj(250)],AREA-100,True,1);self.c.update([obj(250)],AREA-100,True,1.5);self.assertEqual(self.total(),0)
    def test_single_line_not_a_counting_zone(self):
        self.inside();self.c.update([obj(310)],None,True,1);self.assertEqual(self.total(),0)
    def test_return_and_exit_same_track_still_once(self):
        self.inside();self.exit();self.feed(280,2.5);self.feed(250,3);self.feed(250,3.5);self.feed(280,4);self.feed(310,4.5);self.feed(310,5);self.assertEqual(self.total(),1)
    def test_long_occlusion_cannot_prove_exit(self):
        self.inside();self.feed(310,4);self.feed(310,4.5);self.assertEqual(self.total(),0)
    def test_two_separate_objects(self):
        for t,x in [(0,250),(.5,250),(1,280),(1.5,310),(2,310)]:
            self.c.update([obj(x,140),obj(x,250)],AREA,True,t)
        self.assertEqual(self.total(),2)
    def test_paper_delayed_results_can_count(self):
        for t,x in [(2,250),(3,250),(4,280),(5,310),(6,310)]:self.feed(x,t,age=1.3,label='papel / servilleta')
        self.assertEqual(self.total(),1)
    def test_stale_result_not_counted(self):
        self.inside();self.feed(310,2,age=2);self.feed(310,2.5,age=2);self.assertEqual(self.total(),0)
    def test_database_reopens_and_deduplicates(self):
        self.inside();self.exit();self.assertFalse(self.store.record(self.c.session,1,'botella',.8))
        self.assertEqual(EventStore(self.store.path).report()['historical_total'],1)
    def test_session_history_is_separate(self):
        self.inside();self.exit();second=self.store.session();self.assertEqual(self.store.report(second)['total'],0)
        self.assertEqual(self.store.report(self.c.session)['total'],1)
    def test_http_and_csv_real_records(self):
        self.inside();self.exit();server=serve(self.store,0)
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urlopen(base+'/api/estado') as response:self.assertEqual(json.load(response)['total'],1)
            with urlopen(base+'/exportar.csv') as response:self.assertIn('botella',response.read().decode())
            with urlopen(base) as response:self.assertIn('Centro de separación',response.read().decode())
        finally:server.shutdown();server.server_close()

class BoundaryTests(unittest.TestCase):
    def test_near_boundary_allows_motion(self):self.assertTrue(assess_rectangle(AREA,True,(280,150,19,20),0).safe)
    def test_outside_allows_motion_and_negative_clearance(self):
        d=assess_rectangle(AREA,True,(310,150,20,20),0);self.assertTrue(d.safe);self.assertLess(d.clearance,-5)
    def test_missing_tracking_still_blocks(self):self.assertFalse(assess_rectangle(AREA,True,None,0).safe)
    def test_stale_camera_still_blocks(self):self.assertFalse(assess_rectangle(AREA,True,(150,150,20,20),1).safe)
    def test_line_crossing_allows_motion(self):self.assertTrue(assess_line([100,100,300,100],True,(150,70,20,20),1,0).safe)

class GuardTests(unittest.IsolatedAsyncioTestCase):
    async def test_beep_does_not_interrupt_motion(self):
        sent=[];state=CommandState();state.set(True,True,'w',time.monotonic()+1,True);guard=BluetoothGuard(state,'test')
        class Robot:
            def __init__(self,*a):self.client=None
            async def conectar(self):pass
            async def enviar(self,c):
                sent.append(c)
                if c=='p':guard.stop.set()
            async def cerrar(self):pass
        with patch('vision_ranger.RangerBluetooth',Robot):await asyncio.wait_for(guard.run(),1)
        self.assertEqual(sent,['x','0','w','p'])
    async def test_lost_vision_stops_silently(self):
        sent=[];state=CommandState();state.snapshot=(time.monotonic()-2,True,True,'w',time.monotonic()+1,True);guard=BluetoothGuard(state,'test')
        class Robot:
            def __init__(self,*a):self.client=None
            async def conectar(self):pass
            async def enviar(self,c):
                sent.append(c)
                if len(sent)==3:guard.stop.set()
            async def cerrar(self):pass
        with patch('vision_ranger.RangerBluetooth',Robot):await asyncio.wait_for(guard.run(),1)
        self.assertEqual(sent,['x','0','x'])
    async def test_reject_old_firmware_before_movement(self):
        robot=RangerBluetooth();await robot.lineas.put('RANGER_READY_V1')
        with self.assertRaisesRegex(RuntimeError,'Firmware antiguo'):await robot._respuesta(VERSION)

class UpdateTests(unittest.TestCase):
    def test_current_firmware_does_not_flash(self):
        with patch('actualizar_ranger.identify',return_value=VERSION),patch('actualizar_ranger.compile_firmware') as compile:
            self.assertEqual(update('fake',log=lambda _:None),VERSION);compile.assert_not_called()
    def test_unknown_device_is_not_flashed(self):
        with patch('actualizar_ranger.identify',return_value=None),patch('actualizar_ranger.compile_firmware') as compile:
            with self.assertRaises(RuntimeError):update('fake')
            compile.assert_not_called()
    def test_multiple_ports_require_explicit_selection(self):
        with patch('actualizar_ranger.candidates',return_value=['one','two']),patch('actualizar_ranger.update') as upload:
            with self.assertRaises(RuntimeError):update_if_present()
            upload.assert_not_called()
    def test_old_version_uploaded_and_verified(self):
        with patch('actualizar_ranger.identify',side_effect=['RANGER_READY_V1',VERSION]),patch('actualizar_ranger.compile_firmware',return_value=Path('image.hex')),patch('actualizar_ranger.subprocess.run') as run:
            self.assertEqual(update('fake',log=lambda _:None),VERSION)
            self.assertNotIn('-V',run.call_args[0][0])
    def test_failed_flash_never_reports_ready(self):
        import subprocess
        with patch('actualizar_ranger.identify',return_value='RANGER_READY_V1'),patch('actualizar_ranger.compile_firmware',return_value=Path('image.hex')),patch('actualizar_ranger.subprocess.run',side_effect=subprocess.CalledProcessError(1,'avrdude')):
            with self.assertRaises(subprocess.CalledProcessError):update('fake',log=lambda _:None)

class PipelineTests(unittest.TestCase):
    def test_camera_application_persists_confirmed_exit(self):
        import threading
        import vision_linea_robot as app
        class Camera:
            name='CAMARA SIMULADA';index=-1
            def read(self):
                self.index+=1;time.sleep(.1)
                return np.zeros((480,640,3),np.uint8),time.monotonic()
            def close(self):pass
        camera=Camera()
        class Waste:
            status='DETECTOR SIMULADO'
            def __init__(self,*a):self.stop=threading.Event()
            @property
            def latest_details(self):
                x=250 if camera.index<5 else (280 if camera.index==5 else 310)
                return [([x,150,x+20,170],'botella',.8,0)],time.monotonic()
        class Paper:
            status='PAPEL SIMULADO'
            def __init__(self,*a):self.stop=threading.Event()
            def read(self,*a):return []
        class Boundary:
            boundary=AREA;visible=True;tolerance=20
            def update(self,*a):return False
        with tempfile.TemporaryDirectory() as temp:
            store=EventStore(Path(temp)/'test.db')
            from contextlib import ExitStack,redirect_stdout
            import io
            with ExitStack() as stack:
                for name,value in [('Camera',lambda:camera),('WasteDetector',Waste),('PaperDetector',Paper),
                                   ('AutoBoundary',Boundary),('EventStore',lambda:store),('black_lines',lambda *a:[]),
                                   ('black_enclosures',lambda *a:[AREA])]:
                    stack.enter_context(patch.object(app,name,value))
                for name in ['namedWindow','createTrackbar','imshow','destroyAllWindows']:
                    stack.enter_context(patch.object(app.cv2,name))
                stack.enter_context(patch.object(app.cv2,'getTrackbarPos',return_value=30))
                stack.enter_context(patch.object(app.cv2,'getWindowProperty',return_value=1))
                stack.enter_context(patch.object(app.cv2,'waitKey',side_effect=lambda *_:ord('q') if camera.index>=11 else -1))
                stack.enter_context(patch.object(sys,'argv',['vision_linea_robot.py','--solo-vision','--sin-dashboard']))
                with redirect_stdout(io.StringIO()):app.main()
            report=store.report()
            self.assertEqual(report['total'],1)
            self.assertFalse(report['live']['running'])

if __name__=='__main__':unittest.main(verbosity=2)
