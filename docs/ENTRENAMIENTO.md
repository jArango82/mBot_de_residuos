# Recoger imágenes para entrenar el detector

[Inicio](../README.md) · [Uso](USO.md) · [Estado](ESTADO.md)

Los detectores actuales (YOLO-World, Grounding DINO y CLIP) no se entrenaron con tus residuos: reconocen por descripciones de texto y fallan con objetos concretos, como una caja de medicamento blanca y azul. Para entrenar un detector propio hacen falta **fotos de tus residuos reales, tomadas con la misma cámara y en el mismo montaje** que se usará después.

**Estado (26 de octubre de 2026):** hay un primer detector entrenado con tus residuos (`outputs/models/residuos-propio.pt`) y el programa lo usa si existe. Reconoce **caja de cartón, envoltura y papel / servilleta**, pero solo los objetos concretos con los que se entrenó (ver «Primer entrenamiento»). Todavía no hay una herramienta para que etiquetes tú las sesiones nuevas.

## Antes de empezar

1. Monta el teléfono **fijo**, a la misma altura y con el mismo ángulo que usarás con el robot. Deben verse el recuadro de cinta completo y una franja exterior.
2. Abre Camo Studio, con el teléfono transmitiendo con la cámara trasera.
3. Cierra `Detectar_Residuos` u otros programas que usen la cámara.

## Grabar

Abre `outputs/Recoger_Imagenes.command`. Empieza en modo automático: **cada 2 segundos toma una foto y suena un aviso**. Entre aviso y aviso, cambia algo: mueve un residuo, gíralo, quita uno o añade otro. Si quieres hacerlo sin prisa, pulsa `a` para pasar a modo manual y usa `Espacio` para cada foto.

- `Espacio`: guardar una foto ahora.
- `a`: activar o desactivar el modo automático.
- `q`: terminar.

No se guardan las fotos negras o congeladas (cuando Camo no recibe imagen del teléfono). En automático tampoco se guardan las fotos movidas o borrosas. Con `Espacio` se guardan igualmente, con un aviso.

También se puede usar el terminal:

```sh
work/venv/bin/python outputs/recoger_imagenes.py --sesion tarde-luz-lampara --auto --cada 3
```

## Qué fotografiar

Para cada tipo de residuo, intenta que aparezca en **al menos 40-50 fotos**, en situaciones variadas:

- En distintas zonas del recuadro, incluso pegado a la cinta, y alguna vez fuera.
- Girado, dado la vuelta, de pie o tumbado, abierto o aplastado si es posible.
- Junto a otros residuos, tocándose o tapándose un poco.
- Con el robot en la imagen, cerca o tapándolo parcialmente.
- Con distinta luz: de día, de noche, con lámpara o con reflejos.

Haz también algunas fotos **sin ningún residuo** (alrededor de una de cada diez): enseñan al modelo qué no es basura, como el suelo, la cinta, el robot o los reflejos. No fotografíes personas. Si aparece una mano al mover objetos, no pasa nada.

## Sesiones

Cada vez que abres la herramienta se crea una **sesión**: una carpeta con fecha y hora en `work/dataset/imagenes/`, o el nombre que indiques con `--sesion`. Graba **al menos tres sesiones distintas**, en otros momentos, con otra luz o colocando los residuos de otra manera. Al entrenar, una sesión completa se reserva para comprobar el modelo con imágenes que no ha visto; así se sabe si de verdad reconoce los residuos o solo memorizó las fotos.

Como referencia, entre 300 y 500 fotos en total suelen bastar para un primer modelo con pocos tipos de residuo. Con menos se puede probar, pero el resultado será menos fiable.

## Primer entrenamiento

Datos:

- **Para aprender:** tu sesión de 45 fotos (caja naranja y blanca, caja azul y blanca, envoltura blanca con letras rojas y una servilleta grande) y 46 fotogramas de una grabación anterior con el teléfono en la mano (caja naranja y servilleta pequeña).
- **Para comprobar:** 46 fotogramas de la escena con el teléfono fijo (las dos cajas y la servilleta grande). El modelo no aprendió de ellos.

Las cajas de cada foto se marcaron con Grounding DINO, se corrigieron por color y se revisaron una a una a mano. Se añadieron las que faltaban, se quitaron las que no eran residuos y se descartó una foto demasiado movida. Se entrenó YOLO11n (partiendo de `yolo11n.pt`) en la gráfica del Mac: 80 épocas, imágenes de 960 px, giros y volteos aleatorios porque la cámara mira desde arriba. Se guarda el modelo de la última época y no el que mejor puntúa en la prueba, para no hacer trampa.

Resultado en la escena de comprobación: precisión 0,998, exhaustividad 0,996 y mAP50 0,995 sobre 138 objetos. Reproducida en tiempo real, las dos cajas y la servilleta se muestran el 100 % del tiempo, sin etiquetas erróneas. Sin el modelo propio, la caja azul no aparecía nunca.

Límites:

- **Solo conoce esos objetos.** Con fotos de otra cámara y objetos nuevos marcaba suelo o un objeto desconocido como «caja» (confianza 0,26-0,53). Por eso sus detecciones necesitan 0,6 para aparecer, se mantienen desde 0,3 y no pueden ocupar más del 15 % de la imagen. Con esas reglas, esas imágenes ya no muestran nada.
- **La envoltura no se ha comprobado:** solo aparece en las fotos de aprendizaje.
- Para otros residuos (botellas, latas…) siguen trabajando los detectores genéricos. Donde coinciden, manda el modelo propio.

Volver a entrenar, por ejemplo tras añadir sesiones etiquetadas:

```sh
work/venv/bin/python outputs/entrenar_detector.py --prueba NOMBRE_DE_LA_SESION_DE_PRUEBA
```

Las etiquetas revisadas se guardan en `work/dataset/etiquetas/<sesión>.json`; los `.dino.json` son preetiquetas sin revisar y no se usan. Para desactivar el modelo propio: `vision_linea_robot.py --sin-modelo-propio`.

## Privacidad y GitHub

Las fotos se quedan en tu Mac, dentro de `work/`, que no se sube a GitHub. Revisa que no aparezcan personas ni documentos antes de compartirlas con alguien.
