"""Ir hacia un residuo con un robot simulado: rumbo y giro desconocidos que se aprenden moviéndose."""
from pathlib import Path
import math, sys, unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import numpy as np
from navegacion import GoToWaste, angle_diff, box_gap


def simulate(heading, rate, speed, waste=(500,300), start=(150,200), inside=True, noise=1., limit=150, shake=False, push=False):
    """Robot de 40x40 px visto desde arriba. rate: grados/s que gira con «a» en la imagen (con signo).
    shake: cámara en la mano; se gira, se desplaza y se acerca en cada imagen."""
    rng=np.random.default_rng(0)
    nav=GoToWaste(push=push); x,y=start; theta=heading; t=0.; moving=None
    nav.start(t)
    while nav.active and t<limit:
        angle,scale,shift=0.,1.,np.zeros(2)
        if shake:
            angle=math.radians(8*math.sin(t*.7)+rng.normal(0,1)); scale=1+.08*math.sin(t*.4)
            shift=np.array([60*math.sin(t*.5),40*math.cos(t*.3)])+rng.normal(0,3,2)
        rot=np.array([[math.cos(angle),-math.sin(angle)],[math.sin(angle),math.cos(angle)]])
        view=lambda p:scale*rot@np.asarray(p,float)+shift
        # El recuadro visto en esta imagen permite volver a coordenadas del suelo, como hace el programa.
        plane=lambda pts:(np.linalg.inv(rot)@((np.asarray(pts,float).reshape(-1,2)-shift)/scale).T).T
        cx,cy=view((x,y))
        box=(cx-20+rng.normal(0,noise),cy-20+rng.normal(0,noise),40,40)
        wx,wy=view(waste)
        objects=[{'box':[wx-10,wy-10,wx+10,wy+10],'center':[wx,wy],'label':'botella','countable':True,'inside':inside}]
        step=nav.update(t,t,box,objects,plane if shake else None)
        if step:
            moving=(step[0],t+step[1]+.06)   # latencia de Bluetooth
        if moving and t<moving[1]:
            letter=moving[0]
            if letter=='w':
                x+=speed*.05*math.cos(math.radians(theta)); y+=speed*.05*math.sin(math.radians(theta))
            elif letter in 'ad':
                theta+=(rate if letter=='a' else -rate)*.05
        t+=.05
    return nav,(x,y),t


class NavigationTests(unittest.TestCase):
    def test_reaches_waste_whatever_heading_and_turn_direction(self):
        for heading in (0,90,180,-90,135):
            for rate in (150,-150,320):
                for speed in (60,150):
                    nav,(x,y),t=simulate(heading,rate,speed)
                    self.assertIn('Llego',nav.message,f'rumbo {heading}, giro {rate}, velocidad {speed}: {nav.message}')
                    self.assertLess(box_gap([x-20,y-20,x+20,y+20],[490,290,510,310]),nav.arrive+speed*.5)
                    self.assertLess(t,90)

    def test_camera_in_hand_is_compensated_with_the_tape_square(self):
        for heading in (0,120,-150):
            for rate in (150,-200):
                nav,_,t=simulate(heading,rate,100,shake=True)
                self.assertIn('Llego',nav.message,f'rumbo {heading}, giro {rate}: {nav.message}')

    def test_square_is_selected_with_camera_drifting_in_hand(self):
        from vision_boundary import AutoBoundary
        quad=np.float32([[50,50],[550,50],[550,420],[50,420]])
        auto=AutoBoundary();selected=False
        for i in range(10):
            t=i*.06
            selected=auto.update([quad+np.float32([6*i,3*i])],[],t,t) or selected   # deriva de la mano
        self.assertTrue(selected)
        auto.update([quad+200],[],.7,.7)                                            # un salto no es el mismo recuadro
        self.assertFalse(auto.visible)

    def test_turn_direction_is_learned(self):
        nav,_,_=simulate(180,-150,100)
        self.assertLess(nav.turn_rate,0)

    def test_robot_that_does_not_move_is_stopped(self):
        nav,_,_=simulate(0,150,0)
        self.assertIn('no avanza',nav.message)

    def test_no_waste_inside_stops(self):
        nav,start,_=simulate(0,150,100,inside=False)
        self.assertIn('no hay residuos',nav.message)

    def test_lost_robot_stops_and_waits_for_still_image(self):
        nav=GoToWaste(); nav.start(0)
        objects=[{'box':[490,290,510,310],'center':[500,300],'label':'lata','countable':True,'inside':True}]
        self.assertEqual(nav.update(0,0,(100,100,40,40),objects)[0],'w')
        self.assertIsNone(nav.update(.2,.2,(105,100,40,40),objects))       # sigue moviéndose: no mide
        self.assertIsNone(nav.update(.6,.3,(110,100,40,40),objects))       # imagen anterior al final del paso
        nav.update(1,1,None,objects)
        self.assertFalse(nav.active)
        self.assertIn('no seguido',nav.message)

    def test_ambiguous_objects_are_not_targets(self):
        nav=GoToWaste(); nav.start(0)
        objects=[{'box':[490,290,510,310],'center':[500,300],'label':'objeto por identificar','countable':False,'inside':True}]
        self.assertIsNone(nav.update(0,0,(100,100,40,40),objects))
        self.assertIn('no hay residuos',nav.message)

    def test_angle_helpers(self):
        self.assertEqual(angle_diff(170,-170),-20)
        self.assertEqual(box_gap([0,0,10,10],[5,5,20,20]),0)
        self.assertEqual(box_gap([0,0,10,10],[13,14,20,20]),5)


SQUARE = np.array([100., 50.])   # el recuadro va de (100, 50) a (500, 450) en la imagen: 400 x 400 en el plano


def simulate_push(heading, rate, speed, wastes, start=(300, 250), noise=1., limit=240, lag=.06, jumps=0., axis=None,
                  labels=None, sheets=None, tracks=None):
    """Robot de 40x40 y residuos de 20x20 que se mueven al empujarlos con la parte delantera.
    jumps: px de desvío de la caja seguida que cambia de vez en cuando (seguimiento que resbala o se reinicia).
    axis: grados del eje de una lata tumbada. Empujada de punta (a menos de 30° de su eje) no rueda: el robot se le
    sube encima y pasa por arriba. Empujada de lado, rueda delante del robot.
    tracks: grados de error de la dirección de las orugas vista en la imagen (None: no se usa). Como en las
    grabaciones, una de cada diez sale perpendicular y otra no se ve."""
    rng=np.random.default_rng(1); seen_tracks=np.random.default_rng(2)
    nav=GoToWaste(); x,y=start; theta=heading; t=0.; moving=None; drift=np.zeros(2)
    labels=labels or ['lata']*len(wastes)
    # Hojas: {etiqueta: (x1, y1, x2, y2) en la imagen}; el robot las recibe en coordenadas del recuadro.
    goals={k:np.float32([[a,b],[c,b],[c,d],[a,d]])-SQUARE for k,(a,b,c,d) in (sheets or {}).items()}
    wastes=[np.array(w,float) for w in wastes]; worst=0.
    plane=lambda pts:np.asarray(pts,float).reshape(-1,2)-SQUARE
    nav.start(t)
    while nav.active and t<limit:
        if jumps and rng.random()<.15:
            drift=rng.normal(0,jumps,2)
        box=(x-20+drift[0]+rng.normal(0,noise),y-20+drift[1]+rng.normal(0,noise),40,40)
        objects=[]
        for w,label in zip(wastes,labels):
            if box[0]<=w[0]<=box[0]+40 and box[1]<=w[1]<=box[1]+40:
                continue   # el programa no muestra objetos tapados por el robot
            inside=bool(100<w[0]<500 and 50<w[1]<450)
            objects.append({'box':[w[0]-10,w[1]-10,w[0]+10,w[1]+10],'center':list(w),'label':label,'countable':True,'inside':inside})
        nav.sheets=goals                                   # el programa las pasa en cada imagen
        line=None
        if tracks is not None:
            luck=seen_tracks.random()
            line=None if luck<.1 else ((theta+seen_tracks.normal(0,tracks)+(90 if luck<.2 else 0))%180)
        step=nav.update(t,t,box,objects,plane,line)
        if step:
            moving=(step[0],t+step[1]+lag)
        if moving and t<moving[1]:
            letter=moving[0]
            h=np.array([math.cos(math.radians(theta)),math.sin(math.radians(theta))])
            if letter in 'ws':
                x,y=np.array([x,y])+(1 if letter=='w' else -1)*speed*.05*h
                for w in wastes:
                    rel=w-np.array([x,y]); along,lateral=rel@h,rel@np.array([-h[1],h[0]])
                    if letter=='w' and 0<along<30 and abs(lateral)<30:
                        if axis is not None and abs(math.sin(math.radians(theta-axis)))<.5:
                            continue                     # se le sube encima: la lata se queda donde está
                        w[:]=np.array([x,y])+30*h+lateral*np.array([-h[1],h[0]])
            elif letter in 'ad':
                theta+=(rate if letter=='a' else -rate)*.05
        worst=max(worst,max(100-x,x-500,50-y,y-450))
        t+=.05
    return nav,wastes,worst,t


def fully_outside(w):
    return w[0]+10<100 or w[0]-10>500 or w[1]+10<50 or w[1]-10>450


class PushTests(unittest.TestCase):
    def test_waste_is_pushed_out_from_many_starts(self):
        cases=[((150,250),(300,250)),((450,200),(250,300)),((300,90),(300,300)),((260,410),(380,150)),
               ((140,100),(350,350)),((420,380),(150,120))]
        for waste,start in cases:
            for heading in (0,135,-90):
                for rate in (150,-260):
                    nav,(w,),worst,t=simulate_push(heading,rate,110,[waste],start)
                    label=f'residuo {waste}, robot {start}, rumbo {heading}, giro {rate}: {nav.message}'
                    self.assertTrue(fully_outside(w),label)
                    self.assertIn('limpio',nav.message,label)
                    self.assertLess(worst,25,label)   # el robot pisa la cinta, pero no se va del recuadro

    def test_pushes_along_the_robot_waste_line(self):
        # Sin rodeos: va recto al residuo y lo saca por la prolongación de esa línea (aquí, por la derecha),
        # aunque el lado más cercano al residuo sea otro.
        nav,(w,),_,_=simulate_push(180,180,110,[(170,250)],start=(125,250))
        self.assertTrue(fully_outside(w),nav.message)
        self.assertGreater(w[0],500)
        self.assertLess(abs(w[1]-250),80)

    def test_several_wastes_are_all_taken_out(self):
        nav,wastes,worst,t=simulate_push(0,200,110,[(160,200),(440,330),(300,410)])
        self.assertTrue(all(fully_outside(w) for w in wastes),[w.tolist() for w in wastes])
        self.assertIn('3 residuo',nav.message)

    def test_crossing_the_tape_only_while_pushing(self):
        nav=GoToWaste(); nav.start(0)
        self.assertFalse(nav.pushing)
        nav.phase='push'
        self.assertTrue(nav.pushing)

    def test_robot_taken_for_a_waste_is_not_a_target(self):
        nav=GoToWaste(); nav.start(0)
        plane=lambda pts:np.asarray(pts,float).reshape(-1,2)-SQUARE
        fake={'box':[285,235,320,270],'center':[302,252],'label':'caja de carton','countable':True,'inside':True}
        self.assertIsNone(nav.update(0,0,(280,230,40,40),[fake],plane))
        self.assertIn('no hay residuos',nav.message)

    def test_waste_left_half_out_is_pushed_again(self):
        nav=GoToWaste(); nav.start(0); nav.done=[(np.array([-10.,200.]),10.)]
        plane=lambda pts:np.asarray(pts,float).reshape(-1,2)-SQUARE
        half_out={'box':[95,240,115,260],'center':[105,250],'label':'lata','countable':True,'inside':False}
        self.assertIsNone(nav.choose([280,230,320,270],[dict(half_out,observation_age=5)],12,plane,True))  # anterior
        self.assertIsNotNone(nav.choose([280,230,320,270],[dict(half_out,observation_age=.5)],12,plane,True))

    def test_robot_backs_until_its_front_is_inside(self):
        nav=GoToWaste(); nav.start(0)
        plane=lambda pts:np.asarray(pts,float).reshape(-1,2)-SQUARE
        nav.phase,nav.exit,nav.heading='back',(np.array([-1.,0.]),0.),180.
        nav.step('s',.3,0,np.array([20.,200.]))
        step=nav.update(1,1,(90,230,40,40),[],plane)          # centro en x=10 del plano: el morro sigue fuera
        self.assertEqual(step[0],'s')
        nav.update(2,2,(130,230,40,40),[],plane)              # ya dentro: da el residuo por sacado
        self.assertEqual(nav.finished,1)

class NoisyMeasurementTests(unittest.TestCase):
    def test_one_contrary_measurement_does_not_flip_turn_direction(self):
        nav=GoToWaste(); nav.start(0); nav.turn_rate,nav.turn_known=150.,True
        nav.learn_turn(-60,.3)                       # una medida al revés (ruido)
        self.assertGreater(nav.turn_rate,0)
        nav.learn_turn(-60,.3)                       # dos seguidas: entonces sí gira al revés
        self.assertLess(nav.turn_rate,0)

    def test_short_step_after_turn_trusts_the_expected_heading(self):
        nav=GoToWaste(); nav.start(0); nav.turn_rate,nav.turn_known,nav.heading=200.,True,0.
        nav.last_turn=(0.,.3)                        # esperado: 200 * 0,36 = 72 grados
        nav.step('w',.15,0,np.array([100.,100.]))
        nav.measure(np.array([100.,106.]))           # 6 px hacia abajo: 90 grados, casi sin fiabilidad
        self.assertLess(abs(angle_diff(nav.heading,72)),5)
        nav.step('w',.3,1,np.array([100.,100.]))
        nav.measure(np.array([100.,130.]))           # 30 px: se cree la medida
        self.assertLess(abs(angle_diff(nav.heading,90)),1)

    def test_tracking_jumps_still_push_most_wastes_out(self):
        rng=np.random.default_rng(5);done=0
        for _ in range(12):
            waste=(rng.uniform(150,450),rng.uniform(100,400));start=(rng.uniform(150,450),rng.uniform(100,400))
            if np.hypot(*(np.subtract(waste,start)))<60:continue
            nav,(w,),_,_=simulate_push(rng.uniform(-180,180),rng.choice([-1,1])*rng.uniform(100,250),rng.uniform(40,90),
                                       [waste],start,noise=3,lag=.15,limit=300,jumps=6)
            done+=fully_outside(w)
        self.assertGreaterEqual(done,9)


class AutonomyTests(unittest.TestCase):
    def test_robot_outside_the_square_comes_back_by_itself(self):
        # Empieza fuera (a la izquierda de la cinta): no se para, vuelve y saca el residuo.
        for heading in (0,180,90):
            nav,(w,),_,_=simulate_push(heading,160,70,[(330,250)],start=(60,250),noise=3,lag=.15,limit=300)
            self.assertTrue(fully_outside(w),f'rumbo {heading}: {nav.message}')
            self.assertNotIn('salio',nav.message)

    def test_climbing_a_can_tries_another_angle(self):
        # La lata está tumbada a lo largo de la línea de llegada: de frente se le sube encima.
        nav,(w,),_,_=simulate_push(0,160,70,[(330,250)],start=(200,250),noise=2,lag=.15,limit=400,axis=0)
        self.assertTrue(fully_outside(w),nav.message)

    def test_many_lying_cans(self):
        rng=np.random.default_rng(11);done=0;n=0
        for _ in range(25):
            waste=(rng.uniform(150,450),rng.uniform(100,400));start=(rng.uniform(150,450),rng.uniform(100,400))
            if np.hypot(*(np.subtract(waste,start)))<70:continue
            n+=1
            nav,(w,),_,_=simulate_push(rng.uniform(-180,180),rng.choice([-1,1])*rng.uniform(100,250),rng.uniform(40,90),
                                       [waste],start,noise=3,lag=.15,limit=400,axis=rng.uniform(0,180))
            done+=fully_outside(w)
        self.assertGreaterEqual(done,n-1)


RED=(110,300,170,360)       # hoja roja (cajas), abajo a la izquierda dentro del recuadro
YELLOW=(420,70,480,130)     # hoja amarilla (latas), arriba a la derecha


def on(w,sheet):
    # Como el programa (2/11): encima si su centro cae en la hoja o si al menos el 40 % del residuo (20x20) la pisa.
    inside=max(0,min(w[0]+10,sheet[2])-max(w[0]-10,sheet[0]))*max(0,min(w[1]+10,sheet[3])-max(w[1]-10,sheet[1]))
    return bool(sheet[0]<w[0]<sheet[2] and sheet[1]<w[1]<sheet[3] or inside>=.4*400)


class TrackAxisTests(unittest.TestCase):
    """Rumbo por la dirección de las orugas vista en la imagen (2/11)."""
    def test_axis_gives_the_sense_closest_to_what_is_known(self):
        nav=GoToWaste(); nav.axis=170.
        self.assertAlmostEqual(nav.axis_near(-20,35),-10)        # 170 o -10: el más cercano a -20
        self.assertAlmostEqual(nav.axis_near(150,35),170)
        self.assertIsNone(nav.axis_near(80,35))                  # perpendicular: no cuadra, se descarta
        nav.axis=None; self.assertIsNone(nav.axis_near(0,35))

    def test_after_a_turn_the_tracks_replace_the_check_step(self):
        nav=GoToWaste(); nav.start(0)
        nav.heading,nav.turn_rate,nav.turn_known=0.,200.,True
        nav.last_turn=(0.,.3)                                    # giro de unos 70° con «a»
        nav.pending={'letter':'a','seconds':.3,'start':0,'center':np.zeros(2)}
        nav.axis=75.; nav.measure(np.zeros(2))
        self.assertIsNone(nav.last_turn)                         # ya sabe hacia dónde mira: sin comprobación
        self.assertAlmostEqual(nav.heading,75.)
        nav.last_turn=(75.,.3); nav.pending={'letter':'a','seconds':.3,'start':0,'center':np.zeros(2)}
        nav.axis=60.; nav.measure(np.zeros(2))                   # no cuadra con el giro (esperaba ~147°)
        self.assertIsNotNone(nav.last_turn)                      # se comprueba como siempre

    def test_sheets_with_tracks_need_few_check_steps(self):
        import navegacion
        checks=[0]; original=navegacion.GoToWaste.check_step
        def counted(self,*a,**k):
            checks[0]+=1; return original(self,*a,**k)
        rng=np.random.default_rng(5);done=n=0
        with patch.object(navegacion.GoToWaste,'check_step',counted):
            while n<10:
                box=(rng.uniform(150,450),rng.uniform(120,400));can=(rng.uniform(150,450),rng.uniform(120,400))
                start=(rng.uniform(150,450),rng.uniform(150,420))
                if min(np.hypot(*np.subtract(box,can)),np.hypot(*np.subtract(box,start)),np.hypot(*np.subtract(can,start)))<70:continue
                if on(box,RED) or on(can,YELLOW):continue
                n+=1
                nav,(b,c),_,_=simulate_push(rng.uniform(-180,180),rng.choice([-1,1])*rng.uniform(100,250),rng.uniform(40,90),
                                            [box,can],start,noise=3,lag=.15,limit=500,jumps=4,tracks=5,
                                            labels=['caja de carton','lata'],sheets={'caja de carton':RED,'lata':YELLOW})
                done+=on(b,RED) and on(c,YELLOW)
        self.assertGreaterEqual(done,8)                          # 56 de 60 en el banco de pruebas
        self.assertLess(checks[0]/n,14)                          # sin orugas, unas 22 por escena


class SheetTests(unittest.TestCase):
    def test_box_goes_to_the_red_sheet_and_can_to_the_yellow(self):
        # Escenas al azar (caja, lata y robot separados). En simulación: 46 de 49 escenas con las dos en su hoja; si el
        # camino de uno pasa por encima del otro, a veces los arrastra juntos.
        rng=np.random.default_rng(5);done=n=0
        while n<14:
            box=(rng.uniform(150,450),rng.uniform(120,400));can=(rng.uniform(150,450),rng.uniform(120,400))
            start=(rng.uniform(150,450),rng.uniform(150,420))
            if min(np.hypot(*np.subtract(box,can)),np.hypot(*np.subtract(box,start)),np.hypot(*np.subtract(can,start)))<70:continue
            if on(box,RED) or on(can,YELLOW):continue
            n+=1
            nav,(b,c),_,_=simulate_push(rng.uniform(-180,180),rng.choice([-1,1])*rng.uniform(100,250),rng.uniform(40,90),
                                        [box,can],start,noise=3,lag=.15,limit=500,jumps=4,
                                        labels=['caja de carton','lata'],sheets={'caja de carton':RED,'lata':YELLOW})
            done+=on(b,RED) and on(c,YELLOW)
        self.assertGreaterEqual(done,12)

    def test_without_its_sheet_it_is_taken_out(self):
        nav,(b,),_,_=simulate_push(0,160,70,[(300,250)],start=(200,250),noise=2,lag=.15,limit=300,
                                   labels=['caja de carton'],sheets={'lata':YELLOW})
        self.assertTrue(fully_outside(b),nav.message)

    def test_waste_mostly_on_its_sheet_is_left_alone(self):
        nav=GoToWaste(); nav.start(0)
        nav.sheets={'lata':np.float32([[a,b],[c,b],[c,d],[a,d]]) for a,b,c,d in [(np.array(YELLOW)-[100,50,100,50])]}
        plane=lambda pts:np.asarray(pts,float).reshape(-1,2)-SQUARE
        # Hoja amarilla en la imagen: x 420-480, y 70-130. Lata larga con el centro (417, 100) fuera y el 45 % dentro.
        can={'box':[385,92,449,108],'center':[417,100],'label':'lata','countable':True,'inside':True}
        self.assertIsNone(nav.update(0,0,(280,230,40,40),[can],plane))

    def test_waste_already_on_its_sheet_is_left_alone(self):
        nav=GoToWaste(); nav.start(0)
        nav.sheets={'lata':np.float32([[a,b],[c,b],[c,d],[a,d]]) for a,b,c,d in [(np.array(YELLOW)-[100,50,100,50])]}
        plane=lambda pts:np.asarray(pts,float).reshape(-1,2)-SQUARE
        can={'box':[440,90,460,110],'center':[450,100],'label':'lata','countable':True,'inside':True}
        self.assertIsNone(nav.update(0,0,(280,230,40,40),[can],plane))
        self.assertIn('no hay residuos',nav.message)


if __name__=='__main__':unittest.main()
