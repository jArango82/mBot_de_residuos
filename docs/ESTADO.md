# Estado real del proyecto

Actualizado: 2 de noviembre de 2026

¿Empiezas desde cero? Lee primero la [Guía de estudio](GUIA_DE_ESTUDIO.md).

[Inicio](../README.md) · [Uso](USO.md) · [Arquitectura](ARQUITECTURA.md) · [Problemas](PROBLEMAS.md)

Este documento dice **qué funciona de verdad y cómo lo sabemos**. Usamos tres niveles; al exponer, conviene no mezclarlos:

| Nivel | Qué significa |
|---|---|
| **Implementado** | El código existe y pasa las pruebas automáticas, pero no se ha visto funcionar con el robot real. |
| **Probado en simulación** | Se comprobó con un robot y una cámara simulados en el ordenador, con ruido y retrasos parecidos a los reales. Sirve para encontrar fallos; no demuestra que funcione en el suelo. |
| **Probado físicamente** | Se vio funcionar con el robot, la cámara y los residuos reales (en casa de Juan, con luz de día y la cámara fija). |

## En pocas palabras

Una cámara (un Samsung Galaxy S24 Ultra conectado al Mac con la aplicación Camo) mira desde arriba un recuadro de cinta negra en el suelo. Dentro del recuadro hay dos hojas de papel de color. El programa reconoce cinco tipos de residuo y el robot mBot Ranger. Al pulsar **G**, el robot empuja cada residuo hasta su hoja:

- Hoja **amarilla**, residuos **aprovechables**: caja de cartón, lata, botella de vidrio y botella de plástico.
- Hoja **roja**, residuos **peligrosos**: envase de blanqueador. Si el programa duda entre botella de plástico y blanqueador, lo trata como peligroso.

Un panel web (http://127.0.0.1:8765) muestra la cámara en vivo y cuenta cada residuo que queda sobre su hoja. Cada residuo contado se envía a **n8n**, que lo apunta como fila en una hoja de Google Sheets y responde al panel.

## Estado de cada parte

| Parte | Estado | Evidencia |
|---|---|---|
| Cámara externa (Samsung por Camo; LifeCam también sirve) | Probado físicamente | En uso desde el 26/10. La cámara del Mac se rechaza siempre. |
| Recuadro de cinta automático | Probado físicamente **con la cámara fija** | Reconocido desde el principio en todas las pruebas del 2/11. Con el teléfono en la mano no llegó a confirmarse (prueba del 27/10). |
| Hojas amarilla y roja | Probado físicamente | Reconocidas en las pruebas del 2/11, también con un residuo encima. |
| Detector de los cinco residuos | Probado físicamente, **salvo la botella de vidrio** | Prueba del 2/11 (unos 15 min): lata vista en el 97 % de las imágenes, plástico 89 %, caja 84 %, blanqueador 80 %, vidrio solo 5 %. |
| Robot reconocido solo, sin etiqueta | Probado físicamente | El detector propio del robot se usó en todas las pruebas del 2/11. Seleccionarlo con el ratón (`R`) queda de respaldo. |
| Hacia dónde mira el robot, por sus orugas | Probado físicamente | En uso desde el 2/11. Error mediano medido: 5°. |
| Firmware V2 en la placa del robot | Probado físicamente | Cargado el 27/10. Responde por USB y por Bluetooth. |
| Llevar cada residuo a su hoja (tecla G) | Probado físicamente | 2/11, 14:02: blanqueador a la hoja roja y caja a la amarilla, contados a la primera. Ese día también llegaron a la amarilla la botella de plástico y la lata. |
| Sacar del recuadro un residuo sin hoja | Probado físicamente con una versión anterior | 27-29/10, antes de que existieran las hojas. Hoy solo se usa si un residuo no tiene hoja asignada. |
| Conteo y panel web con cámara en vivo | Probado físicamente | Contó en las pruebas del 2/11 (ver la cronología). |
| Registro en Google Sheets con n8n | Probado físicamente | 2/11, 14:02: filas escritas en Google Sheets y respuesta de n8n en el panel en unos 2 s. |
| Ruta óptima entre residuos, pinza para recoger | No existe | El robot va al residuo más cercano con el camino libre y lo empuja. |
| Sensor de línea del robot | No se usa | Requisito antiguo aplazado a propósito (ver [Pendiente_Sensor_Linea.md](../outputs/Pendiente_Sensor_Linea.md)). |
| Cámara en Windows o Linux | No existe | El código de cámara usa AVFoundation, que solo hay en Mac. En esos sistemas solo funciona la consola Bluetooth, y sin probar. |
| Pruebas automáticas | 149 pruebas, todas pasan (comprobado el 2/11, unos 20 s) | `work/venv/bin/python -m unittest discover -s tests`. No usan cámara ni robot. |

## Cronología de las pruebas físicas

| Fecha | Qué se probó | Resultado |
|---|---|---|
| 29/9 | Primer receptor cargado por USB | LED, buzzer y respuestas por Bluetooth correctas. Sin movimiento. |
| 26/10 | Samsung como cámara, por Camo | Imagen del recuadro a ~30 imágenes por segundo y recuadro elegido solo. Robot sin moverse. |
| 27/10 | Firmware V2 cargado. Primeras pruebas con `G` | El robot llegó al residuo y, en otra prueba, sacó residuos del recuadro y llegó a «Recuadro limpio» varias veces. Fallos: seguimiento perdido al empujar, robot tomado por «caja», robot que quedaba fuera. |
| 27/10 | Cámara en la mano | El robot se encontró solo, pero el recuadro no llegó a confirmarse (imagen muy movida). |
| 28/10 | 3.ª prueba del empuje fuera del recuadro | 6 salidas contadas, pero 11 paradas por «el robot salió del recuadro» y latas pisadas. Se cambió: ahora el robot vuelve solo. |
| 29/10 | 4.ª prueba del empuje | 5 salidas contadas (2 cajas, 3 latas), 2 veces «Recuadro limpio», ninguna parada por salir. 8 avisos falsos de «se subió encima» (corregido después). |
| 1/11 | Grabación con las hojas y poca luz | Sirvió para corregir dobles detecciones (la hoja roja tomada por «caja»). La prueba de la tarde no llegó a empezar: imagen borrosa y teléfono sin batería. |
| 2/11, 11:32 | Primera prueba en vivo de las cinco clases (~15 min) | El robot llevó plástico, lata y caja a la amarilla y el blanqueador a la roja; el panel contó 5. Fallos: Bluetooth cortado al empujar, un blanqueador no contado, vidrio casi nunca visto. Corregidos el conteo y el Bluetooth. |
| 2/11, 12:02 | Con esos arreglos | Caja a la amarilla y blanqueador a la roja, contados a la primera. |
| 2/11, 12:24 | Ajustes de giro | Fue peor; Juan pidió volver a la versión anterior. |
| 2/11, 12:44-12:48 | Primera versión del rumbo por las orugas | «Daba vueltas en su sitio». Se corrigió: nunca dos giros seguidos sin avanzar, y un residuo cuenta como dejado si el 40 % de él pisa la hoja. |
| 2/11, 12:55 | Orugas corregidas | Blanqueador a la roja en ~13 s, contado a la primera. Después, una caja pegada a la cinta: el robot salió del recuadro para colocarse detrás, se perdió de vista y se cortó el Bluetooth (problema abierto). |
| 2/11, 13:00 | Repetición | Blanqueador a la roja y caja a la amarilla, los dos contados; «Todo clasificado». |
| 2/11, 13:54 | Con n8n | Panel con «Automatización n8n: CONECTADO». El blanqueador resbaló junto a la hoja y no se contó; corregido. |
| 2/11, 14:02 | Versión actual | Blanqueador a la roja y caja a la amarilla, contados a la primera, apuntados en Google Sheets, respuesta de n8n en el panel en ~2 s. |

## Resultados medidos

Todas las cifras salen de mediciones reales en el Mac del proyecto. Son escenas pequeñas y de una sola casa: **no son precisiones generales**.

**Detector de los cinco residuos** (`residuos-propio.pt`, entrenado el 1/11 con 959 fotos):

| Clase | Fotos no usadas para aprender (80, misma sesión y escena) | En vivo, 2/11 (% de imágenes en que se vio) |
|---|---|---|
| Caja de cartón | 100 % | 84 % |
| Lata | 82-83 % | 97 % |
| Botella de vidrio | 72-88 % | 5 % |
| Botella de plástico | 89 % | 89 % |
| Envase de blanqueador | 96-99 % | 80 % |

Las dos cifras de la primera columna dependen de cuánto se exige que la caja dibujada coincida con la real. En esas fotos de prueba no hubo ninguna confusión entre plástico y blanqueador. Ojo: las fotos de prueba son de la misma sesión de fotos que las de aprendizaje (otro momento de la grabación), así que la cifra es optimista. En vivo, el vidrio tumbado se confundía con una lata; **se decidió no seguir con el vidrio**.

**Detector del robot** (`robot-propio.pt`, 28/10): encontró el robot en 74 de 74 imágenes no vistas y no inventó ninguno en 9 imágenes sin robot, en ~11 ms. El método anterior (Grounding DINO) lo encontraba en 1 de esas 74.

**Rumbo por las orugas** (2/11): comparado con hacia dónde se movió de verdad el robot en 88 tramos rectos de 9 grabaciones, error mediano 5°, el 81 % por debajo de 15°, y un 10 % de errores grandes (toma la dirección perpendicular), que la navegación descarta. Antes, el rumbo se medía con pasos de prueba y tenía unos 20° de error.

**Simulación** (no son pruebas físicas):

- Llevar blanqueador y lata a sus hojas (2/11), 60 escenas con ruido y retraso: 56 bien, unos 30 s por escena. Antes de usar las orugas eran 51 bien y 38 s.
- Sacar residuos del recuadro, el modo anterior sin hojas (28/10): 139 de 139 escenas bien en cada uno de tres escenarios de velocidad.

## Lo que no hace (todavía)

- No elige una ruta óptima: va al residuo más cercano que tenga el camino libre.
- No recoge: empuja. No tiene pinza.
- No usa el sensor de línea del robot.
- No funciona la cámara en Windows ni Linux.
- No se ha medido el retraso real de la imagen de Camo.
- No se ha comprobado en condiciones de exposición (otra luz, otro suelo, gente alrededor).

## Problemas abiertos

Resumen; la explicación y qué hacer están en [Problemas](PROBLEMAS.md#problemas-conocidos-del-prototipo).

1. **Residuos pegados a la cinta**: para colocarse detrás, el robot sale del recuadro y puede perderse de vista.
2. **Todavía gira bastante** para colocarse detrás de cada residuo (unos 15 s con la caja).
3. **La botella de vidrio se detecta poco** (decidido no seguir con ella).
4. **El Bluetooth puede cortarse**: hay que pulsar C, E y G.
5. **«Recuadro perdido» desarma el robot** a propósito: hay que pulsar E y G.
6. **Recuadro frágil** si la cámara se mueve o la luz es mala.
7. **La hoja amarilla es pequeña**: un residuo empujado puede sacar a otro; Juan recoge a mano cada residuo en cuanto se cuenta.
8. **Solo funciona en Mac.**

## Decisiones que se mantienen

- Siempre una cámara externa; la del Mac, nunca.
- Sin etiqueta impresa en el robot: se reconoce por su aspecto.
- Los LED del robot van apagados durante la visión (su luz confundía el seguimiento).
- A mano, el robot puede acercarse a la cinta y cruzarla; el buzzer avisa al salir. En automático tampoco se para al salir: vuelve solo.
- Se conservan todas las paradas de seguridad (ver [Operación](OPERACION_V2.md#seguridad-cuándo-se-para-el-robot)).
- El sensor de línea no se activa.
