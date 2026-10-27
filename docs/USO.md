# Manual de uso

[Inicio](../README.md) · [Instalación](INSTALACION.md) · [Bluetooth](ROBOT.md)

Los comandos de cámara de esta guía son para **Mac con el entorno y los modelos instalados**. Escríbelos desde la raíz del proyecto. Para las teclas, haz clic en la ventana de vídeo y usa letras minúsculas, sin Shift. En la consola Bluetooth, en cambio, cada orden se confirma con Enter.

## Cámara: LifeCam o Samsung Galaxy

El programa usa siempre una cámara externa, **nunca la del Mac**. Si hay una sola cámara reconocida conectada, la elige sola: Microsoft LifeCam, un teléfono Samsung (nombre con «Samsung», «Galaxy» o «Android») o Camo. Si no encuentra ninguna, se detiene y muestra la lista de cámaras que ve el Mac.

Para usar el **Samsung Galaxy S24 Ultra**:

1. Conéctalo con un cable USB-C de datos, abre la notificación USB del teléfono y elige **Cámara web**, si aparece en tu versión de software.
2. Si no aparece, instala **Camo** en el teléfono y **Camo Studio** en el Mac (USB o Wi-Fi), y activa su extensión de cámara para que otras aplicaciones reciban el vídeo.
3. Comprueba qué cámaras ve el Mac:

```sh
work/venv/bin/python outputs/vision_linea_robot.py --listar-camaras
```

4. Abre el programa como siempre. Si hay más de una cámara reconocida, o el teléfono aparece con otro nombre, elígela: `--camara samsung`, `--camara camo`, `--camara lifecam`, parte del nombre o su número en la lista.

Coloca el teléfono **en horizontal**, fijo, encima de la zona. Su imagen suele ser 16:9: más ancha y menos alta que la de la LifeCam. Comprueba que se vean los cuatro lados del recuadro y una franja exterior.

**Resolución.** Con el teléfono se piden hasta 1280 px de lado mayor, con la misma proporción que entrega la cámara, para no deformarla ni añadir bandas negras. El borde, el seguimiento del robot, el conteo y el dashboard trabajan con una copia reducida a 640 px de lado mayor (640 × 360 en 16:9), la misma escala con la que se ajustaron para la LifeCam. La imagen original se usa en el zoom y en los detectores del recorte ampliado: con el teléfono, el zoom muestra detalle real en vez de solo agrandar píxeles. `--resolucion 1920x1080` pide más detalle, con más carga y, en Camo por Wi-Fi, posiblemente más retraso. Al arrancar se indica el tamaño que entrega realmente la cámara, y el panel muestra tamaño y fps.

**Imagen congelada.** Una cámara virtual como Camo puede repetir la última imagen si se corta el teléfono. Si el robot lleva más de 0,6 s en marcha sin ningún cambio en la imagen, se detiene y deshabilita; vuelve a habilitar con `e` después de revisar la cámara. Con el robot quieto no se exige cambio, porque una escena inmóvil puede producir imágenes idénticas. El programa no mide el retraso de la imagen: compruébalo, por ejemplo, filmando un cronómetro en la pantalla del Mac.

Con Camo gratuito aparece su logo en la esquina inferior derecha; el programa ignora lo que se detecte sobre él. No dejes residuos en esa esquina de la imagen.

**Detección con el teléfono.** El detector general usa la gráfica del Mac (si existe) y analiza la imagen del teléfono a 1280 px; sin gráfica vuelve al procesador a 640 px. Una caja que ya se sigue se mantiene con puntuaciones más bajas que las necesarias para crear una nueva, y su nombre es el más votado en los últimos instantes, para que no parpadee ni cambie por una sola imagen. Una propuesta «objeto por identificar» ya no oculta una detección concreta en el mismo sitio. El papel o la servilleta blanca arrugada se confundía con una envoltura; ahora un objeto arrugado **sin color** se nombra papel (una envoltura de plástico blanco o transparente también saldría como papel), y las cajas de cartón ya no se toman por envolturas: el detector de papel también reconoce cajas pequeñas (por ejemplo, de medicamento), que el detector general apenas veía. Con zoom, ese detector alterna la zona ampliada con la imagen completa. Un objeto quieto se sigue mostrando entre reconocimientos (hasta 20 s) mientras conserve su aspecto en el mismo sitio; si se retira, desaparece. Para contarlo como separado hacen falta reconocimientos recientes. Cuanto más lejos esté el teléfono, más pequeños se ven los residuos y peor se detectan: **móntalo fijo** y lo más cerca posible, viendo aún todo el recuadro.

**Detector entrenado con tus residuos.** Si existe `outputs/models/residuos-propio.pt` (ver [Entrenamiento](ENTRENAMIENTO.md)), el panel muestra «modelo propio» y sus detecciones tienen prioridad donde coinciden con las de los detectores genéricos. Solo reconoce los objetos con los que se entrenó. `--sin-modelo-propio` lo desactiva y `--modelo-propio RUTA` usa otro archivo.

Un teléfono Samsung conectado por USB tampoco se confunde con el Ranger al conectar Bluetooth o actualizar el firmware: sus puertos serie se excluyen.

Esta adaptación está probada con simulaciones, no todavía con el teléfono real.

## 1. Ver residuos sin robot

```sh
work/venv/bin/python outputs/vision_linea_robot.py --solo-vision
```

Equivale a abrir `outputs/Detectar_Residuos.command`. No conecta Bluetooth ni necesita Ranger. Fija la cámara encima de la superficie, con iluminación uniforme, y coloca los objetos visibles y separados al principio. No hace falta marcarlos con el ratón.

Se dibujan cajas con etiquetas y puntuaciones. **Botella** no distingue vidrio de plástico. Las categorías configuradas incluyen latas, vasos, cartón, bolsas, envolturas, tapas, platos, cubiertos y restos de comida; la existencia de una categoría no garantiza que reconozca todos sus ejemplos. Papel y servilletas pasan por un detector adicional y una verificación que puede preferir no etiquetar objetos ambiguos.

La puntuación no es una certeza de que sea basura. Una botella utilizable también puede detectarse. `seguimiento` significa que la posición se sigue entre reconocimientos; no es una nueva clasificación en cada imagen. El papel puede tardar más en aparecer que el vídeo.

- `t`: borrar el borde y buscarlo de nuevo.
- `q`: cerrar la prueba.

Los residuos se detectan incluso sin recuadro. Con borde confirmado, el diagnóstico distingue centros dentro/fuera; los objetos exteriores no se ocultan en este modo. Ninguna de estas detecciones ordena al robot acercarse.

### Zoom e inspección de objetos

En la ventana de cámara, usa los botones **+** y **−** o las teclas `+`/`=` y `-`. El zoom digital va de 1× a 4×, en pasos de 0,25. Haz clic sobre el objeto para centrar la vista y amplía; también puedes desplazarte con un clic en la miniatura de la esquina superior derecha. **Vista completa** o `0` restablecen 1×.

El detector general analiza tanto la imagen completa como el recorte ampliado. El detector de papel y envolturas prioriza el recorte seleccionado. Las coordenadas se convierten de nuevo a la imagen original, las cajas duplicadas se unen y los objetos cortados por el recorte se descartan de ese análisis. El seguimiento del Ranger, el borde y el conteo siguen trabajando con la imagen completa, independientemente del zoom. La selección del robot con `r` también utiliza la imagen completa.

Puedes iniciar ampliado con `--zoom 2`. El zoom no mueve físicamente el lente ni mejora su enfoque óptico. La LifeCam conectada ofrece hasta 640 × 480: ampliar ayuda a inspeccionar y a ciertos reconocimientos, pero no crea detalle nuevo. Con el teléfono, el recorte sale de su imagen original de mayor resolución y sí contiene más detalle, hasta el límite de lo que capta su lente. Acerca físicamente la cámara si necesitas más detalle, manteniendo visible el recinto completo.

La prueba con un rollo de cinta mostró confusión con tapas de botella. Los resultados de esa clase se presentan ahora en amarillo como **objeto por identificar**. Un análisis adicional busca esos objetos pequeños, pero no afirma que sean tapas o rollos. No se suman a residuos separados ni a los indicadores del dashboard. Una identificación morada de papel/envoltura tiene prioridad sobre una propuesta ambigua coincidente. Para reconocer rollos como clase fiable se necesitan ejemplos y validación adicionales; cambiar el nombre de la etiqueta no entrena al modelo.

### Mejora de resolución con IA

Pulsa el botón **IA** o la tecla `i` para alternar entre zoom normal y superresolución FSRCNN ×2. Al activarla se establece al menos 2× de zoom; haz clic sobre el residuo para centrar el detalle. `0` / **Vista completa** también apaga la mejora. Se puede arrancar con `--mejora-ia --zoom 2`.

La mejora funciona localmente sobre la **vista ampliada**. El detector, el seguimiento, la vigilancia del borde y el conteo reciben los fotogramas originales. La salida de IA tiene el doble de ancho y alto del recorte, y luego se ajusta a la ventana. No transforma la webcam en una cámara HD real, no recupera necesariamente letras o texturas ausentes y no garantiza mejorar la clasificación. Usa `i` para comparar. El panel muestra el tiempo de procesamiento; si una pasada supera 150 ms, se desactiva para recuperar la respuesta del vídeo.

El modelo es opcional y se obtiene con:

```sh
work/venv/bin/python outputs/preparar_modelos.py --solo-superres
```

Se descarga una versión fija de aproximadamente 39 KB y se verifica su SHA-256. Si falta o falla, continúa la cámara con zoom normal. Los pesos quedan excluidos de GitHub. La preparación completa de modelos también lo incluye.

Implementación basada en [la interfaz oficial de OpenCV](https://docs.opencv.org/4.x/d5/d29/tutorial_dnn_superres_upscale_image_single.html), usando [FSRCNN TensorFlow](https://github.com/Saafke/FSRCNN_Tensorflow) (licencia Apache-2.0, revisión `6a4812c4ef1c4f5947d79beafa32a05a6eb4a94d`). La prueba local del recorte de 320×240 produjo 640×480 en aproximadamente 17 ms después de la primera pasada; es una medición aislada, no una garantía del rendimiento con todos los detectores activos.

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

El programa principal acepta `--modelo RUTA`, `--clases clase1,clase2`, `--nombre NOMBRE_BLE`, `--conectar`, `--velocidad-max`, `--margen`, `--solo-vision`, `--zoom`, `--mejora-ia`, `--diagnostico`, `--dashboard-port`, `--sin-dashboard`, `--camara`, `--resolucion` y `--listar-camaras`. `--clases` filtra nombres existentes; no entrena ni crea categorías nuevas. `--conectar` solo conecta automáticamente en el modo con robot, no habilita movimientos. Sin `--camara` se elige la única cámara externa reconocida.

Consulta las opciones exactas sin abrir la cámara:

```sh
work/venv/bin/python outputs/vision_linea_robot.py --help
work/venv/bin/python outputs/vision_linea.py --help
work/venv/bin/python outputs/vision_ranger.py --help
```
