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

    def test_seen_outside_once_then_lost_counts(self):
        # Fuera, junto a los muebles, el detector lo pierde: una posición fuera que nada contradice durante 1 s basta.
        self.inside();self.feed(310,1);self.c.update([],AREA,True,2.1);self.assertEqual(self.total(),1)

    def test_seen_outside_once_then_back_inside_is_not_exit(self):
        self.inside();self.feed(310,1);self.feed(250,1.5);self.c.update([],AREA,True,3);self.assertEqual(self.total(),0)
    def test_partial_box_outside_does_not_count(self):
        self.inside();self.feed(290,1);self.feed(290,1.5);self.assertEqual(self.total(),0)
    def test_same_detection_repeated_does_not_confirm(self):
        self.feed(250,0);self.feed(250,.5,age=.5);self.feed(310,1);self.feed(310,1.5);self.assertEqual(self.total(),0)
    def test_lost_border_keeps_position_inside(self):
        # Posición anterior (dentro) y nueva (fuera) en coordenadas del recuadro: perder la cinta un rato no la borra.
        self.inside();self.c.update([],None,False,1);self.c.update([obj(300)],AREA,False,1.5);self.exit()
        self.assertEqual(self.total(),1)
    def test_relocated_border_does_not_create_exit(self):
        self.inside();self.c.update([obj(250)],AREA-100,True,1);self.c.update([obj(250)],AREA-100,True,1.5);self.assertEqual(self.total(),0)
    def test_single_line_not_a_counting_zone(self):
        self.inside();self.c.update([obj(310)],None,True,1);self.assertEqual(self.total(),0)
    def test_return_and_exit_same_track_still_once(self):
        self.inside();self.exit();self.feed(280,2.5);self.feed(250,3);self.feed(250,3.5);self.feed(280,4);self.feed(310,4.5);self.feed(310,5);self.assertEqual(self.total(),1)

    def test_put_back_inside_and_taken_out_again_counts_again(self):
        # En la exposición se vuelve a colocar el residuo: si se queda dentro (2 s o más), la nueva salida cuenta.
        self.inside();self.exit()
        for t in (3,3.5,4,4.5,5,5.5):self.feed(250,t)
        self.feed(280,6);self.feed(310,6.5);self.feed(310,7);self.assertEqual(self.total(),2)
    def test_hidden_while_pushed_then_seen_outside_counts(self):
        # Tapado por el robot unos segundos mientras lo empuja; aparece fuera cerca de donde estaba.
        self.inside();self.feed(310,4);self.feed(310,4.5);self.assertEqual(self.total(),1)

    def test_far_object_of_same_type_is_another_one(self):
        # Otra botella que ya estaba fuera, lejos, no demuestra que la de dentro saliera.
        self.inside();self.feed(250,1)
        for t in (1.5,2,2.5):self.c.update([obj(250),obj(30,30)],AREA,True,t)
        self.assertEqual(self.total(),0)

    def test_camera_moved_then_exit_counts(self):
        self.inside()
        shift=np.float32([40,25])
        for t,x in [(.8,250),(1.2,280),(1.6,310),(2.1,310)]:
            self.c.update([obj(x+40,175)],AREA+shift,True,t)       # cámara movida: recuadro y residuo a la vez
        self.assertEqual(self.total(),1)

    def test_leaving_the_image_through_a_side_at_its_edge(self):
        near=np.float32([[100,100],[300,100],[300,470],[100,470]])  # lado de abajo junto al borde de la imagen
        for t,y in [(0,400),(.5,400),(1,440)]:self.c.update([obj(200,y)],near,True,t,shape=(480,640))
        self.c.update([],near,True,2,shape=(480,640),robot=[180,430,240,470])   # tapado por el robot: aún no
        self.assertEqual(self.total(),0)
        self.c.update([],near,True,3,shape=(480,640));self.assertEqual(self.total(),1)

    def test_pushed_onto_tape_at_image_edge_counts(self):
        # Empujado sobre la cinta de abajo, que está junto al borde de la imagen: solo se ve su mitad de dentro.
        near=np.float32([[100,100],[300,100],[300,470],[100,470]])
        for t,y in [(0,400),(.5,400)]:self.c.update([obj(200,y)],near,True,t,shape=(480,640))
        for t in (1,1.5,2):self.c.update([dict(obj(200,462),box=[200,462,220,480])],near,True,t,shape=(480,640))
        self.assertEqual(self.total(),1)

    def test_robot_pushed_it_out_and_it_is_not_seen_inside_again(self):
        self.inside();self.feed(280,1)                    # junto a la cinta derecha (x 300 = 400 en el recuadro)
        self.c.pushed_out('botella',[420,200],1.2)
        self.c.update([],AREA,True,2);self.assertEqual(self.total(),0)
        self.c.update([],AREA,True,3.3);self.assertEqual(self.total(),1)

    def test_robot_claim_is_ignored_if_it_is_still_inside(self):
        self.inside();self.feed(280,1);self.c.pushed_out('botella',[420,200],1.2)
        for t in (2,2.5,3,3.5):self.feed(250,t)
        self.assertEqual(self.total(),0)

    SHEET={'botella':np.float32([[300,0],[400,0],[400,100],[300,100]])}   # en el plano: imagen x 250-300, y 100-150

    def sheet_feed(self,x,y,t):return self.c.update([obj(x,y)],AREA,True,t,sheets=self.SHEET)

    def test_placed_on_its_sheet_counts_once(self):
        self.sheet_feed(200,170,0);self.sheet_feed(200,170,.5)          # fuera de su hoja
        self.sheet_feed(230,140,1);self.sheet_feed(260,110,1.5)         # empujado hasta encima
        self.sheet_feed(262,112,2);self.sheet_feed(262,112,3)
        self.assertEqual(self.total(),1)

    def test_already_on_its_sheet_is_not_counted(self):
        for t in (0,.5,1,1.5):self.sheet_feed(260,110,t)
        self.assertEqual(self.total(),0)

    def test_leaving_the_square_does_not_count_when_it_has_a_sheet(self):
        for t,x in [(0,250),(.5,250),(1,280),(1.5,310),(2,310),(3.5,310)]:self.sheet_feed(x,200,t)
        self.assertEqual(self.total(),0)

    def test_placed_seen_once_then_hidden_by_the_robot_counts(self):
        self.sheet_feed(200,170,0);self.sheet_feed(200,170,.5);self.sheet_feed(230,140,1);self.sheet_feed(262,112,1.5)
        self.c.update([],AREA,True,2.6,sheets=self.SHEET);self.assertEqual(self.total(),1)

    def test_long_waste_mostly_on_its_sheet_counts(self):
        # 2/11: el blanqueador, largo, con el cuerpo sobre la hoja roja y el centro justo fuera del borde.
        long=lambda x,y:dict(box=[x,y,x+60,y+16],label='botella',confidence=.8,observation_age=0)
        for t in (0,.5,1,1.5):self.c.update([long(160,170)],AREA,True,t,sheets=self.SHEET)   # lejos de la hoja
        for t in (2,2.5,3.5):self.c.update([long(215,115)],AREA,True,t,sheets=self.SHEET)    # centro en x 245: fuera
        self.assertEqual(self.total(),1)

    def test_glimpse_on_its_sheet_while_pushed_counts_once(self):
        # Prueba del 2/11: visto un instante sobre la hoja mientras el robot lo empujaba (contado al taparlo), luego
        # visto al lado durante 14 s y, al dejarlo de verdad, otra vez. Es un solo residuo.
        for t in (0,.5,1):self.sheet_feed(200,170,t)
        self.sheet_feed(230,140,1.5);self.sheet_feed(262,112,2);self.c.update([],AREA,True,3.2,sheets=self.SHEET)
        self.assertEqual(self.total(),1)
        for t in range(4,18):self.sheet_feed(240,140,t)                  # al lado de la hoja
        for t in (19,19.5,20.5):self.sheet_feed(262,112,t)
        self.assertEqual(self.total(),1)

    def test_taken_off_its_sheet_later_and_put_back_counts_again(self):
        for t in (0,.5,1,1.5):self.sheet_feed(200,170,t)
        for t in (2,2.5,3):self.sheet_feed(262,112,t)
        for t in (10,10.5,11,12.5):self.sheet_feed(200,170,t)            # quitado a mano tras un rato
        for t in (14,14.5,15.5):self.sheet_feed(262,112,t)
        self.assertEqual(self.total(),2)

    def test_placed_after_a_stray_old_sighting_nearby_counts(self):
        # Prueba del 2/11: una detección suelta junto a la hoja 40 s antes no debe quedarse con la identidad.
        self.sheet_feed(240,140,0);self.sheet_feed(240,140,.2)
        for t in (40,40.5,41,41.5):self.sheet_feed(200,170,t)            # fuera de su hoja, confirmado
        self.c.update([],AREA,True,43,sheets=self.SHEET)                 # tapado por el robot al empujarlo
        self.sheet_feed(262,112,44);self.sheet_feed(262,112,44.5);self.sheet_feed(262,112,45.5)
        self.assertEqual(self.total(),1)

    def test_placed_where_it_was_left_by_hand_long_ago_counts(self):
        # Prueba del 2/11 (imagen 770): colocado a mano sobre la hoja, retirado, y 50 s después el robot lo lleva allí.
        for t in (0,.3,.6,.9):self.sheet_feed(262,112,t)                 # sobre la hoja (no cuenta: ya estaba)
        for t in (50,50.5,51,51.5):self.sheet_feed(200,170,t)            # fuera de la hoja, confirmado
        self.c.update([],AREA,True,53,sheets=self.SHEET)                 # tapado por el robot al empujarlo
        for t in (55,55.5,56.5):self.sheet_feed(263,113,t)
        self.assertEqual(self.total(),1)

    def test_one_already_on_its_sheet_is_not_counted_when_another_is_hidden(self):
        for t in (0,.5,1,1.5):
            self.c.update([obj(262,112),obj(160,200)],AREA,True,t,sheets=self.SHEET)
        for t in (2,2.5,3,3.5,4):                                         # el de fuera queda tapado; el de la hoja sigue
            self.sheet_feed(262,112,t)
        self.assertEqual(self.total(),0)

    def test_disappearing_where_outside_is_visible_is_not_exit(self):
        for t,y in [(0,250),(.5,250),(1,250)]:self.c.update([obj(285,y)],AREA,True,t,shape=(480,640))
        self.c.update([],AREA,True,4,shape=(480,640));self.assertEqual(self.total(),0)
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

    def test_live_camera_on_the_dashboard(self):
        import threading
        from urllib.error import HTTPError
        from dashboard import LiveVideo
        plain=serve(self.store,0)
        try:
            with self.assertRaises(HTTPError) as error:urlopen(f'http://127.0.0.1:{plain.server_port}/video.mjpg')
            self.assertEqual(error.exception.code,503)                         # sin cámara en este proceso
        finally:plain.shutdown();plain.server_close()
        video=LiveVideo();server=serve(self.store,0,video)
        try:
            base=f'http://127.0.0.1:{server.server_port}'
            with urlopen(base) as response:self.assertIn('id="video"',response.read().decode())
            self.assertFalse(video.wanted())                                   # nadie mira: no se codifica
            frame=b'\xff\xd8imagen\xff\xd9'
            def publish():
                for _ in range(40):
                    time.sleep(.05)
                    if video.wanted():video.publish(frame)
            threading.Thread(target=publish,daemon=True).start()
            with urlopen(base+'/video.mjpg',timeout=5) as response:
                self.assertIn('multipart/x-mixed-replace',response.headers['Content-Type'])
                part=response.read(120)
            self.assertIn(b'Content-Type: image/jpeg',part);self.assertIn(frame,part)
            with urlopen(base+'/foto.jpg') as response:self.assertEqual(response.read(),frame)
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
    async def test_one_slow_confirmation_does_not_disconnect(self):
        sent=[];state=CommandState();state.set(True,True,'w',time.monotonic()+5,False);guard=BluetoothGuard(state,'test')
        class Robot:
            def __init__(self,*a):self.client=None
            async def conectar(self):pass
            async def enviar(self,c):
                sent.append(c);state.set(True,True,'w',time.monotonic()+5,False)   # la imagen sigue llegando
                if len(sent)==3:await asyncio.sleep(1)      # una confirmación que no llega a tiempo
                if len(sent)==5:guard.stop.set()
            async def cerrar(self):pass
        with patch('vision_ranger.RangerBluetooth',Robot):await asyncio.wait_for(guard.run(),3)
        # Tras el retraso la orden ya es vieja: para ('x') y sigue, sin desconectarse.
        self.assertEqual(sent,['x','0','w','x','w'])
        self.assertNotIn('detenido',guard.status)
    async def test_three_slow_confirmations_disconnect(self):
        sent=[];state=CommandState();state.set(True,True,'w',time.monotonic()+5,False);guard=BluetoothGuard(state,'test')
        class Robot:
            def __init__(self,*a):self.client=None
            async def conectar(self):pass
            async def enviar(self,c):
                sent.append(c);state.set(True,True,'w',time.monotonic()+5,False)
                if len(sent)>2:await asyncio.sleep(1)      # enlace caído: nada se confirma
            async def cerrar(self):pass
        with patch('vision_ranger.RangerBluetooth',Robot):await asyncio.wait_for(guard.run(),3)
        self.assertEqual(sent,['x','0','w','x','x'])
        self.assertIn('Bluetooth detenido',guard.status)
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
            def __init__(self,*a,**kwargs):self.stop=threading.Event()
            @property
            def latest_details(self):
                x=250 if camera.index<5 else (280 if camera.index==5 else 310)
                return [([x,150,x+20,170],'botella',.8,0)],time.monotonic()
        class Paper:
            status='PAPEL SIMULADO'
            def __init__(self,*a,**kwargs):self.stop=threading.Event()
            def read(self,*a):return []
        class Boundary:
            boundary=AREA;visible=True;tolerance=20
            def update(self,*a,**k):return False
        with tempfile.TemporaryDirectory() as temp:
            store=EventStore(Path(temp)/'test.db')
            from contextlib import ExitStack,redirect_stdout
            import io
            with ExitStack() as stack:
                for name,value in [('Camera',lambda *a:camera),('WasteDetector',Waste),('PaperDetector',Paper),
                                   ('AutoBoundary',Boundary),('EventStore',lambda:store),('black_lines',lambda *a:[]),
                                   ('tape_squares',lambda *a:[AREA])]:
                    stack.enter_context(patch.object(app,name,value))
                for name in ['namedWindow','createTrackbar','setMouseCallback','imshow','destroyAllWindows']:
                    stack.enter_context(patch.object(app.cv2,name))
                stack.enter_context(patch.object(app.cv2,'getTrackbarPos',return_value=30))
                stack.enter_context(patch.object(app.cv2,'getWindowProperty',return_value=1))
                stack.enter_context(patch.object(app.cv2,'waitKey',side_effect=lambda *_:ord('q') if camera.index>=11 else -1))
                stack.enter_context(patch.object(sys,'argv',['vision_linea_robot.py','--solo-vision','--sin-dashboard']))
                with redirect_stdout(io.StringIO()):app.main()
            report=store.report()
            self.assertEqual(report['total'],1)
            self.assertFalse(report['live']['running'])

class RobotSearchTests(unittest.TestCase):
    def test_robot_is_tracked_without_selecting_it(self):
        import threading
        import vision_linea_robot as app
        texture=np.random.default_rng(5).integers(0,255,(360,640,3),np.uint8)
        class Camera:
            name='CAMARA SIMULADA';index=-1
            def read(self):
                self.index+=1;time.sleep(.1)
                return texture.copy(),time.monotonic()
            def close(self):pass
        camera=Camera()
        class Waste:
            status='DETECTOR SIMULADO'
            def __init__(self,*a,**kwargs):self.stop=threading.Event();self.latest_details=([],0)
        class Paper:
            status='PAPEL SIMULADO'
            def __init__(self,*a,**kwargs):self.stop=threading.Event();self.want_robot=False
            def read(self,*a):return []
            @property
            def robot(self):
                # Un análisis nuevo cada dos imágenes, siempre en el mismo sitio, junto al recuadro.
                return ([(np.array([300.,150,340,190]),.72)],camera.index//2) if self.want_robot else ([],0)
        class Boundary:
            boundary=AREA;visible=True;tolerance=20
            def update(self,*a,**k):return False
        with tempfile.TemporaryDirectory() as temp:
            from contextlib import ExitStack,redirect_stdout
            import io
            with ExitStack() as stack:
                for name,value in [('Camera',lambda *a:camera),('WasteDetector',Waste),('PaperDetector',Paper),
                                   ('AutoBoundary',Boundary),('EventStore',lambda:EventStore(Path(temp)/'t.db')),
                                   ('black_lines',lambda *a:[]),('tape_squares',lambda *a:[AREA])]:
                    stack.enter_context(patch.object(app,name,value))
                for name in ['namedWindow','createTrackbar','setMouseCallback','imshow','destroyAllWindows']:
                    stack.enter_context(patch.object(app.cv2,name))
                stack.enter_context(patch.object(app.cv2,'getTrackbarPos',return_value=30))
                stack.enter_context(patch.object(app.cv2,'getWindowProperty',return_value=1))
                stack.enter_context(patch.object(app.cv2,'waitKey',side_effect=lambda *_:ord('q') if camera.index>=25 else -1))
                stack.enter_context(patch.object(sys,'argv',['vision_linea_robot.py','--sin-dashboard','--diagnostico',temp]))
                with redirect_stdout(io.StringIO()):app.main()
            state=json.loads((Path(temp)/'estado.json').read_text())
            self.assertIsNotNone(state['robot_box'])
            np.testing.assert_allclose(state['robot_box'],[300,150,40,40],atol=3)   # el seguimiento puede moverlo 1-2 px

    def test_own_robot_model_finds_robot_and_hides_wastes_on_it(self):
        import threading
        import vision_linea_robot as app
        texture=np.random.default_rng(5).integers(0,255,(360,640,3),np.uint8)
        class Camera:
            name='CAMARA SIMULADA';index=-1
            def read(self):
                self.index+=1;time.sleep(.1)
                return texture.copy(),time.monotonic()
            def close(self):pass
        camera=Camera()
        class Waste:
            status='DETECTOR SIMULADO';robot_ready=True
            def __init__(self,*a,**kwargs):self.stop=threading.Event()
            @property
            def latest_details(self):
                # Una «caja» que es el propio robot y una botella de verdad.
                return [([302,152,338,188],'caja de carton',.8,0),([200,100,220,130],'botella',.8,0)],time.monotonic()
            @property
            def robot(self):
                return ([(np.array([300.,150,340,190]),.9)],time.monotonic()-.05,texture.copy())
        class Paper:
            status='PAPEL SIMULADO'
            def __init__(self,*a,**kwargs):self.stop=threading.Event();self.want_robot=False
            def read(self,*a):return []
            robot=([],0)
        class Boundary:
            boundary=AREA;visible=True;tolerance=20
            def update(self,*a,**k):return False
        with tempfile.TemporaryDirectory() as temp:
            from contextlib import ExitStack,redirect_stdout
            import io
            with ExitStack() as stack:
                for name,value in [('Camera',lambda *a:camera),('WasteDetector',Waste),('PaperDetector',Paper),
                                   ('AutoBoundary',Boundary),('EventStore',lambda:EventStore(Path(temp)/'t.db')),
                                   ('black_lines',lambda *a:[]),('tape_squares',lambda *a:[AREA])]:
                    stack.enter_context(patch.object(app,name,value))
                for name in ['namedWindow','createTrackbar','setMouseCallback','imshow','destroyAllWindows']:
                    stack.enter_context(patch.object(app.cv2,name))
                stack.enter_context(patch.object(app.cv2,'getTrackbarPos',return_value=30))
                stack.enter_context(patch.object(app.cv2,'getWindowProperty',return_value=1))
                stack.enter_context(patch.object(app.cv2,'waitKey',side_effect=lambda *_:ord('q') if camera.index>=12 else -1))
                stack.enter_context(patch.object(sys,'argv',['vision_linea_robot.py','--sin-dashboard','--diagnostico',temp]))
                with redirect_stdout(io.StringIO()):app.main()
            state=json.loads((Path(temp)/'estado.json').read_text())
            np.testing.assert_allclose(state['robot_box'],[300,150,40,40],atol=3)
            self.assertEqual([o['label'] for o in state['objects']],['botella'])


class SheetFinderTests(unittest.TestCase):
    """Hoja roja con un residuo tumbado en diagonal encima (1/11): queda partida en dos triángulos, pero es una hoja."""
    def scene(self, stripe):
        import cv2
        frame=np.full((360,640,3),(150,152,155),np.uint8)
        cv2.rectangle(frame,(200,150),(260,200),(40,40,230),-1)
        cv2.line(frame,(198,148),(262,202),stripe,14)
        return frame

    def test_sheet_split_by_a_bottle_is_found(self):
        from vision_hojas import find_sheets
        sheets=find_sheets(self.scene((175,170,30)),np.float32([[0,0],[640,0],[640,360],[0,360]]))
        self.assertIn('roja',sheets)
        np.testing.assert_allclose(sheets['roja'].min(0),[200,150],atol=4)
        np.testing.assert_allclose(sheets['roja'].max(0),[260,200],atol=4)

    def test_two_red_pieces_separated_by_floor_are_not_a_sheet(self):
        from vision_hojas import find_sheets
        sheets=find_sheets(self.scene((150,152,155)),np.float32([[0,0],[640,0],[640,360],[0,360]]))
        self.assertNotIn('roja',sheets)


if __name__=='__main__':unittest.main(verbosity=2)
