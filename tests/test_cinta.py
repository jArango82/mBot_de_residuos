"""Recuadro de cinta en imágenes sintéticas difíciles: poca luz, sombra, tapado, perspectiva y robot encima."""
from pathlib import Path
import sys, unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'outputs'))
import cv2
import numpy as np
from vision_cinta import tape_squares, square_support, offset

QUAD=np.float32([[170,70],[470,85],[560,310],[90,300]])   # visto en perspectiva


def floor(seed=0, light=200):
    """Suelo claro con vetas finas (como el mármol) y la cinta de 6 px."""
    rng=np.random.default_rng(seed)
    image=np.full((360,640,3),light,np.uint8)
    for _ in range(25):
        p=rng.integers(0,640,2); q=p+rng.integers(-150,150,2)
        cv2.line(image,tuple(map(int,p)),tuple(map(int,q)),(light*.75,)*3,1)
    cv2.polylines(image,[QUAD.astype(np.int32)],True,(25,25,25),6)
    noise=rng.normal(0,4,image.shape)
    return np.clip(image+noise,0,255).astype(np.uint8)


def error(found):
    inner=offset(QUAD,6)
    return min(np.max(np.linalg.norm(np.roll(found,k,axis=0)-inner,axis=1)) for k in range(4))


class TapeSquareTests(unittest.TestCase):
    def assertFound(self,image,**kwargs):
        quads=tape_squares(image,**kwargs)
        self.assertTrue(quads,'no encuentra el recuadro')
        self.assertLess(error(quads[0]),8)

    def test_clean_square_in_perspective(self):
        self.assertFound(floor())

    def test_dim_light(self):
        self.assertFound((floor(1).astype(float)*.3).astype(np.uint8))

    def test_shadow_over_one_corner(self):
        image=floor(2).astype(float)
        image[180:,:260]*=.45                          # sombra de una persona sobre una esquina
        self.assertFound(image.astype(np.uint8))

    def test_person_covering_part_of_a_side(self):
        image=floor(3)
        cv2.ellipse(image,(330,300),(60,40),0,0,360,(40,30,30),-1)   # zapato o pierna sobre el lado de abajo
        self.assertFound(image)

    def test_shadow_edge_is_not_tape(self):
        # Sin cinta: solo el borde recto de una sombra grande. No debe aparecer ningún recuadro.
        image=np.full((360,640,3),200,np.uint8)
        image[:,320:]=70
        image[200:,:]=70
        self.assertEqual(tape_squares(image),[])

    def test_robot_box_is_excluded(self):
        # Un cuadrado oscuro pequeño (el cuerpo del robot) no es el recuadro de cinta.
        image=np.full((360,640,3),200,np.uint8)
        cv2.rectangle(image,(240,110),(420,250),(30,30,30),6)
        self.assertTrue(tape_squares(image))                              # sin saber dónde está el robot, sí
        self.assertEqual(tape_squares(image,exclude=[(230,100,430,260)]),[])

    def test_support_of_known_square(self):
        image=floor(4)
        support=square_support(image,offset(QUAD,6))
        self.assertTrue(np.all(support>.8),support)
        cv2.rectangle(image,(60,250),(600,360),(200,200,200),-1)     # tapa el lado de abajo entero
        support=square_support(image,offset(QUAD,6))
        self.assertGreaterEqual(int(np.sum(support>=.4)),3)          # quedan tres lados: sigue visible

    def test_far_side_thin_and_pale(self):
        # Por la perspectiva, el lado lejano sale fino y pálido (solo un 20-25 % más oscuro que el suelo).
        image=np.full((360,640,3),200,np.uint8)
        a,b,c,d=QUAD.astype(np.int32)
        cv2.line(image,tuple(a),tuple(b),(140,140,140),3)
        for p,q in ((b,c),(c,d),(d,a)):cv2.line(image,tuple(p),tuple(q),(25,25,25),6)
        self.assertFound(image)

    def test_tape_close_to_the_image_edge(self):
        quad=np.float32([[170,6],[470,4],[560,310],[90,300]])   # el lado de arriba casi pegado al borde
        image=np.full((360,640,3),200,np.uint8)
        cv2.polylines(image,[quad.astype(np.int32)],True,(25,25,25),6)
        found=tape_squares(image)
        self.assertTrue(found)
        inner=offset(quad,6)
        self.assertLess(min(np.max(np.linalg.norm(np.roll(found[0],k,axis=0)-inner,axis=1)) for k in range(4)),8)


if __name__=='__main__':unittest.main()
