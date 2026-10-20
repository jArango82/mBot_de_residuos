# Manual de uso

[Inicio](../README.md) · [Instalación](INSTALACION.md) · [Bluetooth](ROBOT.md)

Los comandos de cámara de esta guía son para **Mac con el entorno y los modelos instalados**. Escríbelos desde la raíz del proyecto. Para las teclas, haz clic en la ventana de vídeo y usa letras minúsculas, sin Shift. En la consola Bluetooth, en cambio, cada orden se confirma con Enter.

## 1. Ver residuos sin robot

```sh
work/venv/bin/python outputs/vision_linea_robot.py --solo-vision
```

Equivale a abrir `outputs/Detectar_Residuos.command`. No conecta Bluetooth ni necesita Ranger. Fija la LifeCam encima de la superficie, con iluminación uniforme, y coloca los objetos visibles y separados al principio. No hace falta marcarlos con el ratón.

Se dibujan cajas con etiquetas y puntuaciones. **Botella** no distingue vidrio de plástico. Las categorías configuradas incluyen latas, vasos, cartón, bolsas, envolturas, tapas, platos, cubiertos y restos de comida; la existencia de una categoría no garantiza que reconozca todos sus ejemplos. Papel y servilletas pasan por un detector adicional y una verificación que puede preferir no etiquetar objetos ambiguos.

La puntuación no es una certeza de que sea basura. Una botella utilizable también puede detectarse. `seguimiento` significa que la posición se sigue entre reconocimientos; no es una nueva clasificación en cada imagen. El papel puede tardar más en aparecer que el vídeo.

- `t`: borrar el borde y buscarlo de nuevo.
- `q`: cerrar la prueba.

Los residuos se detectan incluso sin recuadro. Con borde confirmado, el diagnóstico distingue centros dentro/fuera; los objetos exteriores no se ocultan en este modo. Ninguna de estas detecciones ordena al robot acercarse.

### Envolturas pequeñas y cámara inclinada

Desde el 20 de octubre, el detector adicional también busca envolturas de dulces y comida. Analiza con mayor resolución, prueba giros de 90 grados si no encuentra la envoltura y conserva la orientación que funciona. Después compara el recorte en cuatro giros con papel, botellas, piso, cinta, muebles y otros objetos. Solo acepta candidatos que favorezcan la clase envoltura y se repitan en observaciones independientes.

El seguimiento visual puede mantener la etiqueta hasta seis segundos entre reconocimientos; el papel conserva su límite de cuatro segundos. La posición se sigue con la imagen actual, pero la puntuación pertenece al último reconocimiento. Las cajas coincidentes de los dos modelos se unifican para evitar duplicados. El conteo exige nuevos reconocimientos y mantiene su regla dentro → completamente fuera.

No necesita poner la cámara cenital para reconocer esta envoltura. Se verificó en vivo con la webcam inclinada del montaje, ocho muestras consecutivas con detección, y una captura girada en cuatro orientaciones más dos deformaciones de perspectiva simuladas. Esas transformaciones no equivalen a probar todas las vistas físicas posibles. Una envoltura tapada, muy pequeña o de otra apariencia todavía puede omitirse. El primer reconocimiento puede tardar varios segundos mientras explora orientaciones.

## 2. Probar la cinta negra

```sh
work/venv/bin/python outputs/vision_linea.py
```

Equivale a `outputs/Detectar_Linea.command`. Reconoce segmentos oscuros y muestra `LINEA NEGRA DETECTADA` si encuentra alguno. Ajusta `Contraste`: súbelo si confunde juntas del piso y bájalo si no ve la cinta. `q` termina. Este modo no conecta el robot ni delimita por sí solo un área cerrada.

Para detectar un recinto, forma un rectángulo de cinta sobre una superficie más clara. Deben verse sus cuatro lados y las uniones, sin objetos encima de la cinta. Usa la cámara fija y lo más perpendicular posible. Un rectángulo negro relleno no representa el borde esperado.

En el programa principal, los cuatro lados estables se seleccionan automáticamente tras al menos seis imágenes y 0.4 segundos. El dibujo se suaviza para pequeñas variaciones. Si se pierde evidencia del borde, puede conservarse un dibujo naranja, pero eso no significa que el límite esté visible ni que se permita mover el robot. `t` reinicia la selección.

## 3. Probar el Ranger sin etiqueta

Requiere firmware receptor y Bluetooth, además de la instalación de visión:

```sh
work/venv/bin/python outputs/vision_linea_robot.py
```

Equivale a `outputs/Probar_Robot_Linea.command`. Este es el modo actual de robot, sin etiqueta impresa, aunque **sí requiere seleccionar su cuerpo con el ratón**.

1. Coloca el robot en el centro de la zona, con todas las orugas visibles. Espera a la confirmación automática del recuadro.
2. Pulsa `r`, arrastra una selección que incluya TODO el Ranger, orugas y accesorios, y confirma con Enter. Comprueba que el recuadro azul sigue al robot.
3. Pulsa `c` para conectar Bluetooth. La aplicación ordena parar y apaga los LED.
4. Cuando se indique una condición segura y haya conexión, pulsa `e` para habilitar.
5. `w`, `a`, `s`, `d` solicitan pasos de aproximadamente 0.15 segundos: adelante, izquierda, atrás y derecha. La repetición del teclado puede generar nuevas solicitudes.
6. Espacio o `x` paran y deshabilitan. `q` cierra y solicita la parada.

Otros controles:

- `b`: confirmar manualmente un recuadro visible o una única línea. Varios segmentos incompletos no se aceptan como recinto.
- `t`: reiniciar solo la cinta, conservando el seguimiento del robot; deshabilita movimiento.
- `n`: reiniciar cinta y robot; vuelve a seleccionar si moviste la cámara.
- `r`: volver a seleccionar el cuerpo con un límite confirmado y visible.

Si confirmas **una sola línea**, solo vigilas ese límite, no cuatro paredes imaginarias. Coloca el robot en el lado permitido antes de seleccionarlo. Un recuadro nuevo detectado en otra posición exige nueva selección y habilitación; la selección automática del borde no habilita motores por sí sola.

### Aviso de salida y continuidad de manejo

La proximidad y el cruce de cinta ya no bloquean pasos. Solo se pita al confirmar salida del cuerpo, con LEDs apagados. La pérdida de visión/seguimiento sí cancela pasos en silencio. Necesita firmware V2, cuyo pitido no detiene motores. `--velocidad-max` y `--margen` se conservan por compatibilidad con comandos antiguos, pero no aplican frenado por borde en este modo.

Consulta [Operación V2](OPERACION_V2.md) para actualizar por USB, abrir el dashboard y conocer la regla de conteo dentro → completamente fuera. Espacio/`x`, el vencimiento de pasos y el temporizador de comunicación siguen deteniendo motores.

## 4. Modo antiguo con etiqueta

`vision_ranger.py` conserva el programa antiguo si se ejecuta directamente, con sus antiguas decisiones de bloqueo; no lo uses para el nuevo manejo. `outputs/Iniciar_Vision.command` ahora abre el modo actual `vision_linea_robot.py`. Se conserva como alternativa histórica; **no es el inicio recomendado para residuos variados**. Usa YOLO11n para `bottle,cup` y requiere la etiqueta `outputs/Etiqueta_Ranger.png` (ArUco 4x4_50, ID 7).

Imprime el marcador con margen blanco, aproximadamente 6–8 cm de lado, y fíjalo arriba del robot. Confirma el recuadro con `b`, selecciona todo el cuerpo con `r` y Enter, conecta con `c` y habilita con `e`. `w/a/s/d`, espacio/`x`, `n` y `q` conservan las funciones de movimiento, parada, reinicio y salida. No mezcles la calibración de este modo con la del programa sin etiqueta.

## 5. Diagnóstico y opciones

```sh
work/venv/bin/python outputs/vision_linea_robot.py --solo-vision --diagnostico work/diagnostico
```

Guarda y sobrescribe aproximadamente cada segundo `camara.jpg`, `vista.jpg` y `estado.json`. Permite comprobar mensajes, borde, caja del robot, estado BLE y detecciones. Son imágenes reales de tu entorno; se guardan dentro de `work`, excluido de GitHub.

El programa principal acepta `--modelo RUTA`, `--clases clase1,clase2`, `--nombre NOMBRE_BLE`, `--conectar`, `--velocidad-max`, `--margen`, `--solo-vision` y `--diagnostico`, `--dashboard-port` y `--sin-dashboard`. `--clases` filtra nombres existentes; no entrena ni crea categorías nuevas. `--conectar` solo conecta automáticamente en el modo con robot, no habilita movimientos. Este programa no tiene opción `--camara`; la LifeCam se selecciona automáticamente.

Consulta las opciones exactas sin abrir la cámara:

```sh
work/venv/bin/python outputs/vision_linea_robot.py --help
work/venv/bin/python outputs/vision_linea.py --help
work/venv/bin/python outputs/vision_ranger.py --help
```
