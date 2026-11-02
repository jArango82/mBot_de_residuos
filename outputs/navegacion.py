"""Llevar los residuos fuera del recuadro a pasos cortos, vigilado por la cámara.

El robot no lleva etiqueta: la cámara solo ve el rectángulo que lo rodea, no hacia dónde mira. Por eso
el rumbo se mide con su propio movimiento: tras cada paso hacia delante, la dirección en la que se
desplazó es hacia donde mira. Los giros se aprenden igual: se compara el rumbo antes y después de girar.

Con el recuadro conocido, cada residuo se saca empujándolo: el robot va en línea recta hacia el residuo y, al
tocarlo, sigue por esa misma línea hasta que el residuo cruza la cinta. Después retrocede un poco y sigue con
el siguiente. Sin recuadro solo se acerca.

Nada de aquí envía órdenes; devuelve la letra y su duración, y el programa principal las aplica con
las mismas protecciones que los pasos manuales.
"""
import math
import cv2
import numpy as np
from vision_hojas import DESTINO, ON_SHEET, share_on

SIZE = 400.   # lado del recuadro en las coordenadas del plano (el programa lo proyecta a 400 x 400)


def angle_diff(a, b):
    """Diferencia a - b en grados, entre -180 y 180."""
    return (a - b + 180) % 360 - 180


def box_gap(a, b):
    """Hueco en píxeles entre dos cajas [x1, y1, x2, y2]; 0 si se tocan o se solapan."""
    dx = max(0., max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0., max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def covered(box, robot):
    """Fracción de una caja [x1, y1, x2, y2] que cae dentro de la del robot."""
    w = max(0., min(box[2], robot[2]) - max(box[0], robot[0]))
    h = max(0., min(box[3], robot[3]) - max(box[1], robot[1]))
    return w * h / max(1e-6, (box[2] - box[0]) * (box[3] - box[1]))


def corners_of(box):
    x1, y1, x2, y2 = box
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def half_size(points):
    """Mitad del tamaño medio de una caja (en las coordenadas en que estén sus esquinas)."""
    return .25 * (float(np.ptp(points[:, 0])) + float(np.ptp(points[:, 1])))


def heading_of(vector):
    return math.degrees(math.atan2(vector[1], vector[0]))


class GoToWaste:
    def __init__(self, settle=.35, min_move=5., arrive=12., aligned=25., max_time=120.,
                 forward=(.15, .4), turn=(.08, .45), turn_rate=180., speed=120., lag=.06, push=True, reliable=12.):
        self.settle = settle          # s quieto antes de medir dónde quedó
        self.min_move = min_move      # px: un avance menor no permite medir el rumbo
        self.reliable = reliable      # px: desde aquí el rumbo medido se cree del todo (la caja tiembla unos px)
        self.arrive = arrive          # px de hueco entre robot y residuo para darlo por alcanzado (sin empujar)
        self.aligned = aligned        # grados de error aceptados para avanzar en vez de girar
        self.max_time = max_time      # s por residuo
        self.forward, self.turn = forward, turn
        self.initial_rate, self.initial_speed = turn_rate, speed
        self.lag = lag                # s que el robot sigue moviéndose de más (Bluetooth y vigilancia cada 60 ms)
        self.push = push              # con el recuadro conocido, sacar el residuo empujándolo
        self.reset()

    def reset(self):
        self.active = False
        self.message = 'Automatico apagado | G: separar los residuos'
        self.heading = None
        self.target = None
        self.pending = None
        self.last_turn = None
        self.stuck = 0
        # Grados por segundo con signo: positivo si «a» aumenta el ángulo en la imagen. Se corrige solo.
        self.turn_rate = self.initial_rate
        self.turn_known = False
        self.doubt = 0                # medidas seguidas que contradicen el sentido del giro
        self.speed = self.initial_speed
        self.phase = 'go'
        self.plan = {}                # puntos del plano para dibujar: detrás del residuo y salida
        self.exit = None
        self.waste_half = 10.
        self.done = []                # (posición en el plano, instante) de residuos ya sacados
        self.finished = 0
        self.handled = False          # ya se eligió algún residuo (si desaparece de dentro, salió)
        self.backs = 0                # pasos atrás extra tras sacar un residuo
        self.close = False            # yendo hacia un residuo y a punto de tocarlo (puede empujarlo ya)
        self.beep = False             # el programa pita una vez al leerlo
        self.bounded = False          # posiciones en coordenadas del recuadro (0-400)
        self.pushed_out = None        # (etiqueta, punto de salida, instante) del último residuo sacado
        self.queue = []               # pasos para despegarse (retroceder, girar, avanzar) tras subirse a un residuo
        self.side = 1                 # sentido del próximo giro para despegarse (alterna)
        self.seen_waste = None        # última posición vista del residuo que se empuja (coordenadas del recuadro)
        self.tries = []               # (posición, instante) de cada vez que se subió o se atascó con un residuo
        self.skipped = []             # (posición, instante) de residuos que se dejan para más tarde
        self.verified = False         # ya se miró debajo del robot antes de dar el recuadro por limpio
        self.picks = 0                # cuántas veces se eligió un residuo nuevo (para saber si cambió)
        self.sheets = {}              # etiqueta -> cuadrilátero (plano) de la hoja a la que se lleva; lo pone el programa
        self.mode = 'exit'            # 'exit': sacarlo del recuadro; 'goal': llevarlo a su hoja
        self.staged = None            # residuo (pick) para el que el robot ya se colocó detrás
        self.goal_label = None        # clase del residuo que se lleva a su hoja
        self.placed = 0
        self.pushing_pick = None      # el residuo que se está empujando
        self.axis = None              # dirección de las orugas en la imagen actual (0-180), si se ve
        self.last_letter = None       # última orden enviada

    @property
    def pushing(self):
        """Mientras empuja o retrocede, el robot puede pisar la cinta: el residuo tiene que salir."""
        return self.active and (self.phase in ('push', 'back') or (self.phase == 'go' and self.close))

    def start(self, now):
        self.reset()
        self.active = True
        self.started = now
        self.message = 'Automatico: midiendo hacia donde mira el robot'

    def stop(self, message):
        self.active = False
        self.pending = None
        self.message = message

    def choose(self, robot, objects, now, to_plane, in_plane=False):
        """Residuo contable dentro del recuadro más cercano; se conserva el elegido mientras siga visto.
        in_plane: decidir «dentro» con el recuadro (0-400): cuenta también uno que solo ha salido a medias."""
        center = np.array([(robot[0] + robot[2]) / 2, (robot[1] + robot[3]) / 2])
        recent = [(p, t) for p, t in self.done if now - t < 4]
        later = [p for p, t in self.skipped if now - t < 60]

        def inside(o):
            if not in_plane:
                return o.get('inside') is not False
            # Igual que el conteo: sigue «dentro» mientras su centro no haya pasado la cinta más de 12 unidades
            # (antes, uno a medio salir sobre la cinta se daba por sacado y no se contaba).
            c = to_plane([o['center']])[0]
            return bool(min(c[0], c[1], SIZE - c[0], SIZE - c[1]) > -12)
        def stale(o):
            # Un residuo recién sacado puede seguir apareciendo dentro unos instantes: una detección anterior
            # al final del empuje, en el mismo sitio, no cuenta. Una posterior sí (quedó a medias).
            return any(np.linalg.norm(to_plane([o['center']])[0] - p) < 50 and o.get('observation_age', 0) > now - t
                       for p, t in recent)
        # Sin recuadro, se busca uno que no toque al robot. Empujando, puede estar pegado; pero una caja que cae
        # casi entera sobre el robot es el propio robot confundido con un residuo.
        apart = (lambda o: covered(o['box'], robot) < .5) if in_plane else (lambda o: box_gap(robot, o['box']) > 0)
        found = [o for o in objects if o.get('countable', True) and inside(o) and apart(o) and not stale(o) and
                 not any(np.linalg.norm(to_plane([o['center']])[0] - p) < 40 for p in later) and
                 not self.on_goal(o['label'], to_plane([o['center']])[0], 0., to_plane(corners_of(o['box'])))]
        if self.target is not None:
            # Al empujarlo se mueve con el robot: se acepta un salto mayor entre detecciones. Mientras se empuja
            # se sigue también cuando ya está fuera, para saber que salió del todo.
            # Empujándolo, además, toca al robot.
            followed = [o for o in objects if o.get('countable', True) and covered(o['box'], robot) < .5] \
                if self.phase == 'push' else found
            same = [o for o in followed if o['label'] == self.target['label'] and
                    math.dist(o['center'], self.target['center']) < 60]
            if same:
                best = min(same, key=lambda o: math.dist(o['center'], self.target['center']))
                self.target = dict(best, seen=now, pick=self.target.get('pick'))
                return self.target
            # Un residuo quieto puede quedar tapado por el robot al acercarse: se recuerda 5 s.
            if now - self.target['seen'] < 5:
                return self.target
        if not found:
            self.target = None
            return None
        best = min(found, key=lambda o: math.dist(o['center'], center) + self.blocked(o, found, to_plane))
        self.picks += 1
        self.target = dict(best, seen=now, pick=self.picks)
        return self.target

    def update(self, now, stamp, robot_box, objects, plane=None, axis=None):
        """robot_box: (x, y, w, h). Devuelve (letra, segundos) para un paso nuevo, o None.
        axis: dirección de las orugas en el recuadro (grados, 0-180, sin saber cuál es el frente), o None.

        plane convierte puntos de la imagen a coordenadas del recuadro de cinta (0-400). Así, si la cámara se
        mueve (por ejemplo, en la mano), el desplazamiento medido sigue siendo solo el del robot."""
        to_plane = plane or (lambda points: np.asarray(points, float).reshape(-1, 2))
        if not self.active:
            return None
        self.axis = axis
        if now - self.started > self.max_time:
            if not (self.push and plane is not None and self.target is not None):
                self.stop('Automatico detenido: tiempo maximo sin sacar el residuo')
                return None
            # Con un residuo no lo consigue: se deja para más tarde y sigue con los demás.
            self.skip(now, to_plane([self.target['center']])[0])
        if robot_box is None:
            self.stop('Automatico detenido: robot no seguido')
            return None
        x, y, w, h = robot_box
        robot = [x, y, x + w, y + h]
        corners = to_plane(corners_of(robot))
        center = to_plane([[x + w / 2, y + h / 2]])[0]
        if self.pending is not None:
            end = self.pending['start'] + self.pending['seconds'] + self.settle
            # Se mide con una imagen tomada cuando el robot ya está quieto.
            if now < end or stamp < end - .1:
                return None
            backed = self.pending['letter'] == 's'
            self.measure(center)
            if not self.active:
                return None
            if backed and self.phase == 'back' and self.mode == 'goal':
                self.waste_placed(now)
            elif backed and self.phase == 'back':
                u, line = self.exit
                # Si el morro sigue sobre la cinta (el retroceso medido fue corto), otro paso atrás: así el
                # siguiente residuo empieza con el robot dentro. Como mucho tres.
                if center @ u + half_size(corners) > line - 5 and self.backs < 3:
                    self.backs += 1
                    self.message = 'Volviendo dentro del recuadro'
                    return self.step('s', .25, now, center)
                self.waste_out(now)
                if not self.active:
                    return None
        target = self.choose(robot, objects, now, to_plane, plane is not None and self.push)
        self.bounded = plane is not None and self.push
        if plane is not None and self.push:
            return self.push_step(now, center, corners, target, to_plane)
        if target is None:
            self.stop('Automatico: no hay residuos dentro del recuadro')
            return None
        gap = box_gap(robot, target['box'])
        if gap <= self.arrive:
            self.stop(f'Llego al residuo: {target["label"]}')
            self.beep = True
            return None
        return self.go_to(to_plane([target['center']])[0], now, center, f'avanzando hacia {target["label"]} ({gap:.0f} px)')

    def tolerance(self):
        """Grados de error aceptados: no se puede pedir menos que el giro más corto posible."""
        smallest = abs(self.turn_rate) * (self.turn[0] + self.lag) if self.turn_known else 0
        return max(self.aligned, .6 * smallest)

    def push_step(self, now, center, corners, target, to_plane):
        robot_half = half_size(corners)
        # Fuera del recuadro solo se admite el morro al empujar; si no, algo va mal (rumbo o giro mal medidos).
        beyond = max(-center[0], -center[1], center[0] - SIZE, center[1] - SIZE)
        # Empujando, el último paso corto puede llevarlo un paso más allá: luego retrocede.
        slack = 2 * robot_half + self.speed * (self.forward[0] + self.lag) if self.pushing else robot_half
        if beyond > slack and self.phase == 'push':
            # El último paso de empuje lo llevó más allá de lo previsto (robot rápido o retraso): el residuo ya está
            # fuera; se retrocede en vez de parar.
            self.phase, self.backs = 'back', 0
            self.message = 'residuo fuera: retrocediendo'
            return self.step('s', float(np.clip((beyond + robot_half) / self.speed - self.lag, .2, .7)), now, center)
        if self.phase == 'unstick':
            step = self.unstick_step(now, center)
            if step is not None or self.phase == 'unstick':
                return step
        if beyond > slack and self.phase not in ('back', 'return'):
            # Fuera del recuadro no se para (habría que ir a buscarlo): vuelve solo hacia el centro.
            self.phase = 'return'
        if self.phase == 'return':
            if beyond > -(robot_half + 15):
                return self.go_inside(now, center)
            self.phase = 'go'
        fresh = target is not None and target['seen'] == now
        if target is not None:
            box = to_plane(corners_of(target['box']))
            waste = box.mean(axis=0)
            if fresh:
                self.waste_half = half_size(box)
        if self.phase in ('push', 'back') and not fresh and self.heading is not None:
            # Tapado o empujado más deprisa de lo que llega la detección: está delante del robot.
            ahead = np.array([math.cos(math.radians(self.heading)), math.sin(math.radians(self.heading))])
            waste = center + ahead * (robot_half + self.waste_half)
            box = None
        elif target is None:
            if (self.finished or self.handled) and not self.verified:
                # Antes de darlo por limpio, un paso atrás: si se subió a una lata, la tiene debajo y no se ve.
                self.verified = True
                self.message = 'Automatico: comprobando que no quede nada debajo del robot'
                return self.step('s', .4, now, center)
            # Sin número: un residuo que queda al borde de su hoja se vuelve a empujar y se sumaba otra vez (2/11: «5
            # residuos» con 2 en el recuadro). Lo separado de verdad lo cuenta el panel.
            if self.placed and not self.finished:
                self.stop('Todo clasificado: cada residuo en su hoja')
                self.beep = True
            elif self.finished or self.handled:
                self.stop(f'Recuadro limpio: {self.finished} residuo(s) fuera' if self.finished and not self.placed else
                          'Recuadro limpio')
                self.beep = True
            else:
                self.stop('Automatico: no hay residuos dentro del recuadro')
            return None
        label = target['label'] if target is not None else 'residuo'
        self.handled = True
        if self.phase == 'push' and target is not None and target.get('pick') != self.pushing_pick:
            # Se perdió el que empujaba y ahora el objetivo es otro residuo: hay que ir hacia él, no seguir empujando.
            self.phase = 'go'
        if fresh:
            self.verified = False
        # Empujándolo hacia su hoja puede quedar tapado y sin objetivo un momento: se sigue con la misma hoja.
        goal_label = label if target is not None else (self.goal_label if self.mode == 'goal' and self.phase == 'push' else None)
        goal = self.sheets.get(goal_label)
        if goal is not None and self.phase in ('go', 'push') and (self.phase == 'go' or self.mode == 'goal'):
            self.goal_label = goal_label
            quad = box if target is not None and fresh else None
            return self.goal_step(now, center, robot_half, waste, fresh, target or {}, goal_label, np.asarray(goal, float), quad)
        if self.phase == 'go':
            self.mode = 'exit'
            # Sin rodeos: el robot va en línea recta hacia el residuo y, al tocarlo, sigue por esa misma línea
            # empujándolo hasta sacarlo del recuadro. Colocarse antes detrás del residuo exigía mucha precisión con
            # un robot tan pequeño en la imagen y le hacía dar vueltas.
            line = waste - center
            distance = float(np.hypot(*line))
            u = line / max(distance, 1e-6)
            self.set_line(center, waste, u)
            # Un paso más y lo toca: si está junto a la cinta, ese paso ya puede empujarlo fuera.
            self.close = distance < 2 * (robot_half + self.waste_half) + self.speed * (self.forward[1] + self.lag)
            facing = (self.heading is not None and self.last_turn is None and
                      abs(angle_diff(heading_of(line), self.heading)) <= 45)
            # Ya pegado pero mirando hacia otro lado: primero se gira hacia él (go_to); empujar así lo desviaría.
            if distance > robot_half + self.waste_half + 8 or not facing:
                return self.go_to(waste, now, center, f'yendo hacia {label} ({distance:.0f})')
            self.phase = 'push'
            self.pushing_pick = target.get('pick') if target is not None else None
        u, end = self.exit
        if self.phase == 'push':
            if fresh and (waste - center) @ u < -.3 * robot_half and \
                    np.linalg.norm(waste - center) < 2 * robot_half + 3 * self.waste_half:
                # El residuo vuelve a verse, pero detrás del robot: se le subió encima y pasó por arriba (las orugas
                # trepan por las latas tumbadas). Se retrocede y se prueba desde otro ángulo. (Que deje de verse no
                # basta: al empujarlo, el robot lo tapa a menudo; así se detectaban subidas que no eran.)
                self.seen_waste = waste.copy()
                return self.climbed(now, center, 'se subio encima del residuo')
            if fresh:
                self.seen_waste = waste.copy()
            front = center @ u + robot_half
            # Fuera del todo: su borde más cercano al robot ya pasó la cinta. El morro del robot pisa la cinta y,
            # por el retraso, el último paso puede llevarlo algo más allá: retrocede enseguida.
            outside = box is not None and fresh and not np.any((box >= 0).all(axis=1) & (box <= SIZE).all(axis=1))
            # El residuo va delante del robot: con el morro a su tamaño más allá de la cinta, queda fuera del todo.
            if front >= end + 2 * self.waste_half + 10 or outside:
                self.phase = 'back'
                self.backs = 0
                self.message = f'{label} fuera: retrocediendo'
                # Lo necesario para que el morro vuelva 10 px dentro de la cinta.
                seconds = float(np.clip((front - end + 10) / self.speed - self.lag, .2, .7))
                return self.step('s', seconds, now, center)
            v = np.array([-u[1], u[0]])
            # Si el residuo resbaló hacia un lado, ya no está delante: se vuelve a ir hacia él (nueva línea).
            if fresh and abs((waste - center) @ v) > robot_half + .5 * self.waste_half:
                self.phase = 'go'
                return self.go_to(waste, now, center, f'{label} se desvio: yendo otra vez hacia el')
            if self.heading is None or self.last_turn is not None:
                return self.check_step(now, center)
            # Se apunta al residuo si se ve; si no (tapado por el robot), se sigue recto por la línea.
            aim = waste if fresh else center + u * 60
            error = angle_diff(heading_of(aim - center), self.heading)
            if abs(error) > 60:
                self.phase = 'go'
                return self.go_to(aim, now, center, f'girando hacia {label}')
            if abs(error) > self.tolerance():
                return self.turn_by(error, now, center, f'corrigiendo el empuje ({error:+.0f} grados)')
            seconds = float(np.clip(.6 * (end + 2 * self.waste_half + 10 - front) / self.speed - self.lag, *self.forward))
            self.message = f'Automatico: empujando {label} fuera ({max(0., end - front):.0f} hasta la cinta)'
            return self.step('w', seconds, now, center)
        return None

    def blocked(self, item, others, to_plane):
        """Penalización si al llevar ese residuo a su hoja se pasaría por encima de otro (lo arrastraría también):
        se prefiere empezar por los que tienen el camino libre."""
        goal = self.sheets.get(item['label'])
        if goal is None:
            return 0.
        a = to_plane([item['center']])[0]
        b = np.asarray(goal, float).mean(axis=0)
        path = b - a
        for other in others:
            if other is item:
                continue
            p = to_plane([other['center']])[0]
            along = float(np.clip(((p - a) @ path) / max(path @ path, 1e-6), 0, 1))
            if np.linalg.norm(a + path * along - p) < 45:
                return 300.
        return 0.

    def on_goal(self, label, point, margin=0., quad=None):
        """¿Está sobre la hoja de su clase? El punto (plano) encima, o buena parte de su caja quad (plano) encima."""
        goal = self.sheets.get(label)
        if goal is None:
            return False
        if quad is not None and share_on(quad, goal) >= ON_SHEET:
            return True
        return cv2.pointPolygonTest(np.float32(goal), (float(point[0]), float(point[1])), True) > margin

    def goal_step(self, now, center, robot_half, waste, fresh, target, label, goal, quad=None):
        """Llevar el residuo a su hoja: si el robot no está ya detrás del residuo (mirando hacia la hoja), primero se
        coloca detrás; después lo empuja recto hacia el centro de la hoja hasta dejarlo encima."""
        self.mode = 'goal'
        middle = goal.mean(axis=0)
        sheet = DESTINO.get(label, '')
        to_goal = middle - waste
        reach = float(np.hypot(*to_goal))
        ug = to_goal / max(reach, 1e-6)
        vg = np.array([-ug[1], ug[0]])
        behind = waste - ug * (robot_half + self.waste_half + 20)
        self.exit = (ug, float(middle @ ug))
        self.plan = {'robot': center.copy(), 'waste': waste.copy(), 'exit': middle.copy(),
                     'staging': None if self.staged == target.get('pick') else behind.copy()}
        if self.phase == 'push':
            if fresh and self.on_goal(label, waste, -2, quad):
                # Encima de su hoja: retrocede y sigue con el siguiente.
                self.phase, self.backs = 'back', 0
                self.message = f'{label} en la hoja {sheet}: retrocediendo'
                return self.step('s', .35, now, center)
            if fresh and (waste - center) @ ug < -.3 * robot_half and np.linalg.norm(waste - center) < 2 * robot_half + 3 * self.waste_half:
                self.seen_waste = waste.copy()
                return self.climbed(now, center, 'se subio encima del residuo')
            if fresh:
                self.seen_waste = waste.copy()
            front = center @ ug + robot_half
            if not fresh and front >= middle @ ug + self.waste_half:
                # Tapado por el robot, pero el morro ya llegó al centro de la hoja: el residuo está encima.
                self.phase, self.backs = 'back', 0
                self.message = f'{label} en la hoja {sheet}: retrocediendo'
                return self.step('s', .35, now, center)
            # El robot se dirige a la hoja con el residuo delante (así el residuo va hacia la hoja aunque el robot no
            # esté justo detrás). Si el residuo resbala y ya no va delante, se vuelve a colocar detrás.
            course = middle - center
            across = np.array([-course[1], course[0]]) / max(float(np.hypot(*course)), 1e-6)
            if fresh and abs((waste - center) @ across) > .7 * robot_half + .5 * self.waste_half:
                self.phase, self.staged = 'go', None
                return self.go_to(behind, now, center, f'{label} se desvio: colocandose otra vez detras')
            if self.heading is None or self.last_turn is not None:
                return self.check_step(now, center)
            aim = middle
            error = angle_diff(heading_of(aim - center), self.heading)
            if abs(error) > 60:
                self.phase, self.staged = 'go', None
                return self.go_to(behind, now, center, f'colocandose detras de {label}')
            if abs(error) > self.tolerance():
                return self.turn_by(error, now, center, f'corrigiendo el empuje ({error:+.0f} grados)')
            seconds = float(np.clip(.6 * max(reach, 10.) / self.speed - self.lag, *self.forward))
            self.message = f'Automatico: llevando {label} a la hoja {sheet} ({reach:.0f})'
            return self.step('w', seconds, now, center)
        # Ir: ¿está ya detrás del residuo, en la línea hacia la hoja?
        line = waste - center
        distance = float(np.hypot(*line))
        lined_up = line @ ug > 0 and abs(angle_diff(heading_of(line), heading_of(ug))) < (45 if self.staged == target.get('pick') else 30)
        if not lined_up:
            self.staged = None
            # Cada paso corto recorre speed·(0,15 s + retraso): no se pide más precisión que eso.
            if np.linalg.norm(center - behind) > max(30., .5 * self.speed * (self.forward[0] + self.lag)):
                self.close = False
                # Si el camino recto hacia detrás del residuo pasa por encima de él, se rodea por un lado (si no, lo
                # empujaría en otra dirección).
                clear = robot_half + self.waste_half + 10
                path = behind - center
                along = float(np.clip(((waste - center) @ path) / max(path @ path, 1e-6), 0, 1))
                if np.linalg.norm(center + path * along - waste) < clear:
                    side = 1. if (center - waste) @ vg >= 0 else -1.
                    around = waste + vg * side * (clear + 15) - ug * robot_half
                    return self.go_to(around, now, center, f'rodeando {label}')
                return self.go_to(behind, now, center, f'colocandose detras de {label}')
        self.staged = target.get('pick')
        self.close = distance < 2 * (robot_half + self.waste_half) + self.speed * (self.forward[1] + self.lag)
        facing = (self.heading is not None and self.last_turn is None and
                  abs(angle_diff(heading_of(line), self.heading)) <= 45)
        if distance > robot_half + self.waste_half + 8 or not facing:
            return self.go_to(waste, now, center, f'yendo hacia {label} ({distance:.0f})')
        self.phase = 'push'
        self.pushing_pick = target.get('pick')
        return self.goal_step(now, center, robot_half, waste, fresh, target, label, goal, quad)

    def waste_placed(self, now):
        self.done.append((self.plan.get('exit', np.zeros(2)), now))
        self.placed += 1
        self.beep = True
        self.message = 'Residuo en su hoja'
        self.phase = 'go'
        self.mode = 'exit'
        self.target = None
        self.staged = None
        self.plan = {}
        self.started = now

    def climbed(self, now, center, why):
        """Se subió al residuo o se atascó con él: retroceder, girar unos 70° y avanzar un poco, para llegar
        después desde otro ángulo (una lata tumbada empujada de lado rueda en vez de dejarse pisar)."""
        self.prepare_unstick(now, center, why)
        return self.unstick_step(now, center)

    def prepare_unstick(self, now, center, why):
        spot = self.seen_waste if self.seen_waste is not None else center
        self.tries = [(p, t) for p, t in self.tries if now - t < 60] + [(spot.copy(), now)]
        if sum(np.linalg.norm(p - spot) < 60 for p, _ in self.tries) >= 3:
            self.skip(now, spot)
            why += '; se deja para mas tarde'
        self.side = -self.side
        self.queue = [('s', .45), ('turn', 70 * self.side), ('w', .3)]
        self.phase = 'unstick'
        self.seen_waste = None
        self.message = f'Automatico: {why}'

    def skip(self, now, spot):
        self.skipped.append((np.asarray(spot, float).copy(), now))
        self.target = None
        self.phase = 'go'
        self.started = now

    def unstick_step(self, now, center):
        if not self.queue:
            self.phase = 'go'
            return None
        kind, value = self.queue.pop(0)
        if kind == 'turn':
            if self.heading is None:
                self.queue.insert(0, (kind, value))
                return self.check_step(now, center)
            return self.turn_by(value, now, center, 'probando desde otro angulo')
        return self.step(kind, value, now, center)

    def go_inside(self, now, center):
        """Volver al recuadro: hacia su centro; si mira hacia fuera, marcha atrás (sin dar la vuelta)."""
        goal = np.array([SIZE / 2, SIZE / 2])
        if self.heading is None or self.last_turn is not None:
            return self.check_step(now, center)
        error = angle_diff(heading_of(goal - center), self.heading)
        if abs(error) > 120:
            self.message = 'Automatico: volviendo al recuadro (marcha atras)'
            return self.step('s', .35, now, center)
        return self.go_to(goal, now, center, 'volviendo al recuadro')

    def set_line(self, center, waste, u):
        """Línea robot → residuo prolongada hasta la cinta: por ahí saldrá el residuo."""
        steps = [((SIZE if u[k] > 0 else 0.) - waste[k]) / u[k] for k in (0, 1) if abs(u[k]) > 1e-6]
        reach = max(0., min(steps)) if steps else 0.
        self.exit = (u, float(waste @ u + reach))
        self.plan = {'robot': center.copy(), 'waste': waste.copy(), 'exit': waste + u * (reach + self.waste_half + 20)}

    def waste_out(self, now):
        u, line = self.exit
        self.done.append((self.plan.get('exit', np.zeros(2)) - u * 40, now))
        # Para el conteo: qué residuo salió y por dónde (coordenadas del recuadro). El programa lo lee y lo borra.
        self.pushed_out = ((self.target or {}).get('label'), self.plan.get('exit', np.zeros(2)) - u * 40, now)
        self.finished += 1
        self.beep = True
        self.message = f'Residuo fuera del recuadro ({self.finished})'
        self.phase = 'go'
        self.target = None
        self.plan = {}
        self.started = now     # el tiempo máximo cuenta por residuo

    def check_step(self, now, center):
        """Paso corto para medir el rumbo. Tras cada giro se comprueba así: dos giros seguidos podrían sumar más
        de media vuelta y ya no se sabría hacia qué lado giró. Con el recuadro conocido, si hacia delante el
        robot saldría de él (cerca de la cinta), se mide marcha atrás."""
        self.message = 'Automatico: comprobando hacia donde mira el robot'
        letter = 'w'
        if self.bounded and self.heading is not None:
            guess = math.radians(self.heading + (self.turn_rate * self.last_turn[1] if self.last_turn else 0))
            move = self.speed * (self.forward[0] + self.lag) * np.array([math.cos(guess), math.sin(guess)])
            middle = np.array([SIZE / 2, SIZE / 2])
            ahead = center + move
            if (np.any(ahead < 0) or np.any(ahead > SIZE)) and \
                    np.linalg.norm(center - move - middle) < np.linalg.norm(ahead - middle):
                letter = 's'
        # Lo bastante largo para que el desplazamiento se distinga del temblor de la caja.
        seconds = float(np.clip(1.3 * self.reliable / max(self.speed, 20.) - self.lag, self.forward[0], .35))
        return self.step(letter, seconds, now, center)

    def go_to(self, goal, now, center, doing):
        if self.heading is None or self.last_turn is not None:
            return self.check_step(now, center)
        error = angle_diff(heading_of(goal - center), self.heading)
        if abs(error) > self.tolerance():
            return self.turn_by(error, now, center, f'girando ({error:+.0f} grados)')
        # Como mucho un 60 % de la distancia por paso, para no pasarse.
        seconds = float(np.clip(.6 * float(np.hypot(*(goal - center))) / self.speed - self.lag, *self.forward))
        self.message = f'Automatico: {doing}'
        return self.step('w', seconds, now, center)

    def turn_by(self, error, now, center, doing):
        if self.last_letter in ('a', 'd'):
            # Nunca dos giros seguidos: con el rumbo de las orugas, encadenaba giros sin avanzar y daba vueltas en el
            # mismo sitio (2/11). Entre giro y giro, un paso adelante (que además vuelve a medir).
            return self.check_step(now, center)
        if self.turn_known:
            longest = min(self.turn[1], 120 / abs(self.turn_rate))
            seconds = float(np.clip(abs(error) / abs(self.turn_rate) - self.lag, self.turn[0], longest))
        else:
            seconds = .12  # primer giro corto: sirve para aprender cuánto y hacia dónde gira
        letter = 'a' if (error > 0) == (self.turn_rate > 0) else 'd'
        self.last_turn = (self.heading, seconds if letter == 'a' else -seconds)
        self.message = f'Automatico: {doing}'
        return self.step(letter, seconds, now, center)

    def step(self, letter, seconds, now, center):
        self.last_letter = letter
        self.pending = {'letter': letter, 'seconds': seconds, 'start': now, 'center': center.copy()}
        return letter, seconds

    def axis_near(self, reference, limit):
        """Rumbo según las orugas (su eje, en el sentido más cercano a reference) si queda a menos de limit grados de
        reference; si no (o no se ven), None. Las orugas dan la dirección con ~5° de error y sin moverse; el
        desplazamiento de un paso corto, con ~20°."""
        if self.axis is None or reference is None:
            return None
        pick = min((self.axis, self.axis + 180.), key=lambda a: abs(angle_diff(a, reference)))
        return angle_diff(pick, 0) if abs(angle_diff(pick, reference)) <= limit else None

    def turn_from_axis(self):
        """Tras un giro, las orugas dicen hacia dónde quedó el robot: no hace falta el paso de comprobación (2/11:
        girar y comprobar era el 60 % del tiempo). Si no cuadran con el giro hecho, se comprueba como siempre."""
        if self.last_turn is None or self.axis is None or self.last_turn[0] is None:
            return
        before, signed = self.last_turn
        if self.turn_known:
            expected = self.turn_rate * (signed + math.copysign(self.lag, signed))
            seen = self.axis_near(before + expected, 30)
            if seen is None:
                return
            change = angle_diff(seen, before)
            # Solo se aprende de giros claros y parecidos a lo esperado (en vivo, aprender de todos hacía saltar
            # la velocidad de giro entre 55 y 166 °/s).
            if abs(change) >= 20 and .5 <= change / expected <= 2:
                self.learn_turn(change, signed)
        else:
            # Primer giro, corto: el rumbo nuevo es el sentido de las orugas más cercano al de antes.
            seen = self.axis_near(before, 70)
            if seen is None:
                return
            self.learn_turn(angle_diff(seen, before), signed)
        if self.turn_known:
            self.heading, self.last_turn = seen, None

    def measure(self, center):
        step, self.pending = self.pending, None
        if step['letter'] in 'ad':
            self.turn_from_axis()
            return
        if step['letter'] not in 'ws':
            return
        moved = center - step['center']
        distance = float(np.hypot(*moved))
        turn, self.last_turn = self.last_turn, None
        # Rumbo esperado: el anterior si fue en línea recta; tras un giro, lo que se sabe de cómo gira.
        expected = None
        if turn is not None and self.turn_known:
            before, signed = turn
            expected = before + self.turn_rate * (signed + math.copysign(self.lag, signed))
        elif turn is None and self.heading is not None:
            expected = self.heading
        if distance < self.min_move:
            if step['letter'] == 'w':
                self.stuck += 1
                if self.stuck >= 4 and not (self.bounded and len(self.tries) < 6):
                    self.stop('Automatico detenido: el robot no avanza (revisa baterias, orugas o seguimiento)')
                elif self.stuck >= 3 and self.bounded and self.phase in ('go', 'push'):
                    # Atascado (contra un residuo o subido a él): retroceder y probar desde otro ángulo.
                    self.stuck = 0
                    self.prepare_unstick(step['start'], center, 'atascado')
            # Va más despacio de lo que se creía: el próximo paso de comprobación será más largo.
            self.speed = max(20., .7 * self.speed)
            if expected is not None:
                self.heading = angle_diff(expected, 0)
                seen = self.axis_near(self.heading, 35)
                self.heading = self.heading if seen is None else seen
            else:
                self.last_turn = turn   # sin saber cómo gira, hay que volver a comprobarlo
            return
        self.stuck = 0
        # Hacia atrás se mueve al revés de hacia donde mira.
        measured = heading_of(moved) if step['letter'] == 'w' else angle_diff(heading_of(moved), 180)
        self.speed = .5 * self.speed + .5 * distance / (step['seconds'] + self.lag)
        if turn is not None and distance >= self.reliable:
            self.learn_turn(angle_diff(measured, turn[0]), turn[1])
        # La caja seguida tiembla unos píxeles (y salta si el seguimiento se corrige): con un desplazamiento corto
        # el rumbo medido es poco fiable. Se mezcla con el esperado en proporción a lo que se movió.
        trust = min(1., (distance - self.min_move) / (self.reliable - self.min_move))
        self.heading = measured if expected is None else angle_diff(expected + trust * angle_diff(measured, expected), 0)
        # Las orugas, si se ven y cuadran, mandan: mucho más precisas que el desplazamiento.
        seen = self.axis_near(self.heading, 35)
        if seen is not None:
            self.heading = angle_diff(seen + .2 * angle_diff(self.heading, seen), 0)

    def learn_turn(self, change, signed):
        """Grados por segundo con signo que gira «a» con esta cámara, a partir de un giro bien medido."""
        if abs(change) <= 5:
            return
        rate = change / (signed + math.copysign(self.lag, signed))
        if abs(rate) <= 20:
            return
        if not self.turn_known:
            self.turn_rate, self.turn_known = rate, True
        elif (rate > 0) == (self.turn_rate > 0):
            self.turn_rate = .5 * self.turn_rate + .5 * rate
            self.doubt = 0
        else:
            # El sentido del giro no cambia: una medida contraria suele ser ruido. Solo se corrige si se repite.
            self.doubt += 1
            if self.doubt < 2:
                return
            self.turn_rate, self.doubt = rate, 0
        self.turn_rate = math.copysign(min(max(abs(self.turn_rate), 30.), 900.), self.turn_rate)
