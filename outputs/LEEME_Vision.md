# Visión del Ranger desde una webcam externa

## Detección automática de posibles residuos, sin robot

Abre `Detectar_Residuos.command`. Usa la LifeCam externa y marca automáticamente en morado los objetos reconocidos, con su nombre y puntuación. No hace falta seleccionar objetos, imprimir etiquetas ni conectar el Ranger. También selecciona el recuadro de cinta automáticamente. T reinicia el borde y Q cierra.

El modelo predeterminado `models/residuos-world-small.pt` es YOLO-World-S con descripciones de botellas, latas, vasos, cajas y trozos de cartón, papel, bolsas, envolturas, tapas, platos desechables, cubiertos plásticos y restos de comida. Se usa la variante pequeña para mantener fluidez junto al detector de papel. Varias descripciones se agrupan en una sola etiqueta. Las botellas se muestran como **botella**, sin afirmar si son de vidrio o plástico: esa distinción falló en la prueba real. Las descripciones se guardan en `models/residuos-categorias.json`.

El papel tiene un detector adicional local Grounding DINO Tiny (`models/grounding-dino-tiny`), configurado para papel arrugado y servilletas. Se eliminan detecciones que abarcan más del 20% de la imagen para evitar confundir el suelo con papel; por eso esta configuración está orientada a residuos pequeños y no a hojas que llenan el encuadre. Las cajas reconocidas se siguen automáticamente entre análisis, sin selección manual. El análisis es más lento que el vídeo. La etiqueta «seguimiento» indica que la posición se actualiza visualmente entre reconocimientos; la puntuación pertenece al último reconocimiento.

Las otras detecciones se suavizan entre imágenes y toleran interrupciones de hasta 0.7 segundos. Se eliminan al caducar; no se mantienen indefinidamente. El seguimiento del papel caduca tras cuatro segundos sin un nuevo reconocimiento. Estas detecciones no se usan para enviar movimientos al robot.

Para reducir falsas etiquetas de papel, cada candidato también pasa por CLIP local: compara su apariencia con papel, plástico, metal, botellas, muebles, suelo, tela, manos, cartón y objetos desconocidos. Debe favorecer papel y aparecer en dos análisis consecutivos antes de etiquetarse. Si la comparación es ambigua, no se muestra como papel. El ajuste se comprobó con el papel arrugado, la botella y el objeto rígido que el detector confundía en la cámara; no equivale a validar todos los materiales posibles.

Estas categorías son una configuración de detección abierta, **no un entrenamiento validado con residuos de este montaje**. Puede omitir objetos pequeños, aplastados, transparentes u ocultos, o confundir objetos normales con posibles residuos. La puntuación del detector no es una probabilidad calibrada de que algo sea basura. Se deben probar ejemplos reales de cada categoría; no se promete reconocer todos los residuos ni la mayoría en cualquier escena.

Las detecciones funcionan aunque el recuadro aún no esté visible. Cuando el recuadro está confirmado, el diagnóstico indica si el centro del objeto está dentro o fuera, sin ocultar los de fuera. La imagen se analiza localmente; la descarga inicial solo obtiene los modelos. La aplicación no navega hacia los objetos.

Referencia del modelo: [YOLO-World, documentación oficial](https://docs.ultralytics.com/models/yolo-world/).

La parada mediante el seguidor de línea físico queda pendiente según `Pendiente_Sensor_Linea.md`; no se implementó en esta etapa.

## Primero: reconocer una línea negra

Abre `Detectar_Linea.command`. Usa exclusivamente la LifeCam externa y marca en verde los segmentos largos de cinta oscura que encuentra. No necesita cuatro lados ni confirmar con B. Muestra `LINEA NEGRA DETECTADA` cuando encuentra al menos uno. El deslizador `Contraste` permite exigir más diferencia con el piso; súbelo si marca juntas y bájalo si la cinta se ve tenue. Pulsa Q para salir.

Esta etapa es solo de visión: no conecta Bluetooth ni envía comandos al robot. Reconoce segmentos oscuros por su forma y contraste; otros objetos largos y oscuros también pueden coincidir. Una sola línea todavía no define el interior de una zona segura.

## Visión del recuadro y del robot

### Probar una sola línea con el Ranger sin etiqueta

**Selección automática del recuadro:** cuando los cuatro lados aparecen estables en al menos seis imágenes durante 0.4 segundos, se seleccionan solos. No hace falta pulsar B. La posición se suaviza y admite variaciones de hasta 20 píxeles; esos 20 píxeles se añaden al margen de protección. Si falla la detección del contorno, se comprueba si las cuatro líneas siguen respaldando el borde. Si falta esa evidencia, se conserva el dibujo en naranja y se detiene el robot hasta recuperar la visión. Una nueva ubicación estable se selecciona automáticamente, pero exige volver a seleccionar el robot con R y habilitar con E. T reinicia la búsqueda automática. La selección del recuadro nunca habilita movimientos por sí sola.

Abre `Probar_Robot_Linea.command`. Mantén fija la webcam externa, mirando desde arriba. Ahora se muestran todos los segmentos detectados. Si se reconocen los cuatro lados, aparece `RECUADRO: 4 lados detectados` y B confirma el recinto completo; se vigilan todos sus lados. Si solo hay un segmento, B confirma ese único límite. Si hay varios segmentos pero no forman un recuadro reconocido, se pide mejorar el encuadre. R permite seleccionar todo el robot con las orugas y confirmar con Enter. El seguimiento visual CSRT usa esa selección, sin etiqueta impresa. Verifica que el recuadro azul permanezca sobre el robot.

- **T** borra únicamente la cinta; **B** confirma una nueva, conservando el seguimiento del robot. Coloca el robot en el lado permitido antes de confirmar.
- **N** reinicia cinta y robot. Si mueves la cámara, usa N y vuelve a seleccionar ambos.
- **C** conecta Bluetooth y apaga el anillo LED para evitar reflejos que alteren el seguimiento. Al perder línea o robot, o acercarse al límite, envía parada y buzzer, manteniendo los LED apagados.
- **E** habilita pasos cuando hay separación suficiente; W/A/S/D dan pasos cortos. Espacio o X detienen; Q cierra.

Es una prueba supervisada. El seguimiento por apariencia puede confundirse con otros objetos u oclusiones; no garantiza identificación infalible. Se reserva una envolvente que incluye las esquinas del cuerpo seleccionado, incluso al girar, y distancia estimada de frenado. Falta calibrar esa distancia físicamente. Si se confirma una sola línea, únicamente se protege ese límite. Si se confirma el recuadro completo, se comprueban los cuatro lados y se bloquea el movimiento si se pierde el recuadro. La visión se ejecuta en el Mac; el Ranger recibe letras por Bluetooth.

El 29 de septiembre se cargó `ranger_bluetooth.ino` por USB y se verificaron 6626 bytes de memoria. El receptor confirmó parada, LED rojos y buzzer; el usuario confirmó luces y sonido. También respondió al buzzer por Bluetooth con el módulo actual `Makeblock_LE10a56219eb91`. Falta verificar físicamente el seguimiento y la parada automática junto a la línea.

### Modo anterior de recuadro completo

Abre `Iniciar_Vision.command` desde Finder. En este Mac, el programa selecciona automáticamente **Microsoft LifeCam VX-5000**; no usa la cámara integrada como alternativa si falta la LifeCam. El nombre de la cámara aparece en la ventana. El análisis se realiza localmente.

Se corrigió la selección de cámara: OpenCV ordena los dispositivos por identificador, mientras que el listado original de macOS estaba en otro orden. El programa ahora usa el mismo orden que OpenCV y rechaza cualquier índice que corresponda a la cámara del Mac, incluso si se pasa mediante `--camara`. En la comprobación actual, la LifeCam es el índice 0 y la cámara integrada es el 1; esto se calcula de nuevo al abrir, no queda fijado a esos números. [Referencia del backend de OpenCV](https://github.com/opencv/opencv/blob/5.0.0/modules/videoio/src/cap_avfoundation_mac.mm).

## Preparar la zona

1. Coloca la LifeCam fija encima de una superficie plana, mirando lo más perpendicular posible hacia abajo. Deben verse el recuadro entero y el robot.
2. Forma un rectángulo con cinta negra y los **cuatro lados visibles**; no sirve un rectángulo negro relleno. El detector usa el contraste local de la cinta y sus líneas, por lo que admite piso de ladrillos, cinta que aparece gris y pequeñas discontinuidades en las esquinas. No acepta lados ausentes ni huecos grandes. Mantén las uniones cerradas y usa cinta suficientemente ancha para verse en la imagen.
3. Imprime `Etiqueta_Ranger.png`, con el cuadrado negro de unos 6–8 cm de lado. Conserva el margen blanco y colócala plana encima del Ranger, visible desde arriba y firmemente sujeta. El dibujo corresponde a ArUco 4x4_50, ID 7. El programa reconoce esta etiqueta como el robot; no contiene un modelo entrenado para reconocer cualquier mBot sin etiqueta.
4. Coloca el robot cerca del centro, lejos del borde. Para probar objetos, coloca una botella o un vaso en la zona.

## Calibrar cada vez que abres el programa

- El borde candidato se dibuja amarillo y aparece `Recuadro detectado - pulsa B para confirmar`. Ajusta el deslizador `Negro` si hace falta. Pulsa **B** solo cuando el contorno amarillo corresponda al recuadro correcto. Debe mantenerse estable varios fotogramas antes de confirmarlo. El contorno queda ligeramente dentro de la cinta para reservar su grosor.
- Con la etiqueta visible, pulsa **R**. Arrastra un rectángulo que incluya TODO el robot: orugas, chasis y cualquier pala o pinza que sobresalga. Confirma con Enter. Esto calcula una envolvente circular conservadora alrededor de la etiqueta, con holgura adicional.
- Pulsa **C** para conectar el Ranger por Bluetooth. Tiene que estar encendido y desconectado de mBlock, del teléfono y de los otros scripts de control.
- Cuando aparezca `Zona segura`, pulsa **E** para habilitar los movimientos. **W/A/S/D** envían pasos cortos; **Espacio** o **X** paran y bloquean el movimiento. **Q** sale. **N** borra la calibración.
- Si se pierde la cámara, la etiqueta o el borde, o el robot entra en la franja de protección, el movimiento se bloquea. Para volver a habilitarlo, sitúalo manualmente dentro de la zona segura y pulsa E.

No muevas la cámara ni cambies el tamaño del robot después de calibrar. Si lo haces, pulsa N y repite B y R. El robot se puede identificar en cualquier giro; el círculo incluye las esquinas de la selección, incluso al girar.

## Qué hace la protección

El ordenador mide la distancia de la etiqueta al borde interior de la cinta. Antes de permitir un movimiento, exige espacio para todo el robot, un margen adicional y el recorrido estimado hasta que pueda detenerse. También toma en cuenta el movimiento observado entre imágenes.

Al conectar, envía **x** (parar) y **0** (apagar el anillo LED). Durante la visión no enciende luces verdes ni rojas: sus reflejos interfieren con el seguimiento. Ante peligro envía **x** y **p** (buzzer). Mientras persiste el problema, repite la parada y emite un pitido aproximadamente cada dos segundos. Si no hay conexión Bluetooth, muestra el problema pero no puede activar físicamente la alarma. El firmware puede encender verde al reiniciar la placa; la aplicación lo apaga al conectar.

La detección de objetos funciona en otro hilo: una inferencia lenta no debe bloquear la vigilancia del borde. Si la vigilancia deja de actualizarse durante 300 ms, el controlador también ordena detenerse. El receptor cargado en la placa mantiene su parada por falta de comandos de movimiento tras 600 ms.

Esta protección solo controla los movimientos enviados desde **esta ventana**. No ejecutes simultáneamente el control Bluetooth anterior, mBlock ni otra app que envíe órdenes. No existe navegación autónoma hacia los residuos en esta versión.

## Ajustar la distancia de parada

Los valores iniciales son conservadores pero aún no están calibrados en tu montaje: velocidad máxima prevista de 100 píxeles/s, margen adicional de 20 píxeles y reserva de 1.25 s más la antigüedad de la imagen (600 ms del firmware, 300 ms de frescura y 350 ms para transporte/frenado estimado). El firmware actual usa potencia de motor 100/255.

No se puede garantizar que nunca cruce el borde sin medir la velocidad máxima y el frenado reales con la altura de cámara, superficie y baterías utilizadas. Valida primero pasos cortos en el centro de una zona amplia. Ajusta la cota de velocidad a un valor superior al máximo observado y aumenta el margen si hace falta. Si la zona segura queda muy pequeña, amplía la zona física o cambia el encuadre antes de reducir márgenes.

Ejemplo para aumentar las reservas:

```sh
./Iniciar_Vision.command --velocidad-max 180 --margen 30
```

Los valores son píxeles de la imagen capturada, no centímetros. Esta versión está pensada para una vista cenital; una cámara muy inclinada requiere calibración geométrica adicional.

## Detector básico del modo anterior (`Iniciar_Vision.command`)

El modelo local YOLO11n detecta **botellas** (`bottle`) y **vasos/tazas** (`cup`) y los dibuja como *posible residuo*. Identificar un objeto no permite determinar por sí solo si está desechado. Cuando el borde está confirmado y visible, solo se muestran los objetos cuyo centro está dentro; se excluyen los centros dentro de la envolvente del robot calibrado.

El modelo no está entrenado para clasificar latas, papeles arrugados, envolturas o residuos orgánicos como categorías de basura. Para reconocer esas clases se necesitan ejemplos etiquetados y un modelo entrenado. Se puede cargar otro modelo y sus nombres de clases mediante:

```sh
./Iniciar_Vision.command --modelo /ruta/modelo_residuos.pt --clases botella,lata,papel
```

Los nombres deben coincidir exactamente con las clases del modelo. Esta opción no añade clases a un modelo que no las conoce. El programa informa si alguna falta.

## Archivos y estado de verificación

- `vision_ranger.py`: aplicación de cámara, objetos y control Bluetooth.
- `vision_core.py`: detección del recuadro, etiqueta, geometría y decisiones de protección.
- `camaras_mac.py`: selección de la LifeCam usando el orden de dispositivos de OpenCV.
- `ranger_bluetooth.py`: conexión al Ranger ya utilizada en la configuración anterior.
- `models/yolo11n.pt`: modelo de detección instalado localmente.
- `Etiqueta_Ranger.png`: etiqueta imprimible del robot.
- `requirements_vision.txt`: dependencias de esta versión.

Comprobado el 29 de septiembre de 2026, después de corregir la selección: nueva captura de la LifeCam externa a 640×480. La primera comprobación había abierto por error la cámara integrada aunque mostraba el nombre de la externa. Las pruebas de selección cubren ese cambio de orden y rechazan la cámara integrada, índices inexistentes y selecciones ambiguas. Las pruebas sintéticas de visión verifican el borde cerrado, rechazo de contornos abiertos, identificación de la etiqueta, cuerpo cerca/fuera del borde, pérdida de visión y orden de los comandos de alarma.

El detector de recuadro se ajustó con una captura real de cinta sobre ladrillos. La etapa de línea permite reconocer cinta aunque el resto del recuadro quede fuera de la imagen.

**Pendiente de validación física:** falta probar el Ranger identificado dentro de la zona. El Ranger no apareció en la búsqueda Bluetooth de esta sesión; por eso no se verificó físicamente la alarma ni la parada cerca del borde. No se enviaron movimientos.

## Instalación en otro equipo

Python 3.11 o posterior. El acceso de doble clic usa `../work/venv` en este Mac; conserva las carpetas. En otro equipo crea un entorno, instala requirements_vision.txt y ejecuta `python vision_ranger.py`. La captura de cámara actual utiliza AVFoundation y está preparada para macOS. En otro sistema habría que adaptar ese backend.

Referencias: [detección ArUco en OpenCV](https://docs.opencv.org/4.x/d5/dae/tutorial_aruco_detection.html), [detección de objetos con Ultralytics](https://docs.ultralytics.com/modes/predict/), [clases COCO](https://docs.ultralytics.com/datasets/detect/coco/).
