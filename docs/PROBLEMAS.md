# Problemas y soluciones

Actualizado: 2 de noviembre de 2026

¿Empiezas desde cero? Lee primero la [Guía de estudio](GUIA_DE_ESTUDIO.md).

[Inicio](../README.md) · [Instalación](INSTALACION.md) · [Uso](USO.md) · [Estado](ESTADO.md)

Primero, los límites conocidos del prototipo (no son averías: es lo que todavía no está resuelto). Después, soluciones ordenadas por síntoma.

## Problemas conocidos del prototipo

| Problema | Por qué pasa | Qué hacer |
|---|---|---|
| **Residuo pegado a la cinta**: el robot sale del recuadro, se pierde de vista y a veces se corta el Bluetooth. | Para empujar un residuo hacia su hoja, el robot se coloca detrás de él. Si el residuo está junto a la cinta, en el lado contrario a su hoja, «detrás» queda fuera del recuadro, a veces fuera de la imagen. | Coloca los residuos al menos a un robot de distancia de la cinta. Si pasa: Espacio, vuelve a poner el robot dentro y pulsa C (si se cortó), E y G. |
| **El robot gira bastante** antes de empujar. | Colocarse detrás de cada residuo necesita varias maniobras (con la caja, unos 15 s). Ya no da vueltas en su sitio, pero sigue maniobrando. | Es normal en el prototipo. Explícalo en la exposición. |
| **La botella de vidrio casi no se detecta** (5 % de las imágenes en vivo). | Es pequeña; tumbada, el detector la confunde con una lata. | Se decidió no seguir con ella: mejor no usarla en la demostración. |
| **Se corta el Bluetooth** («Bluetooth detenido: …»). | Si tres confirmaciones seguidas del robot tardan más de 0,45 s, el programa cierra la conexión por seguridad. Pasa más si el robot se aleja o queda tapado. | Pulsa **C**, **E** y **G**. Mantén el Mac cerca del recuadro. |
| **«Recuadro perdido o imagen atrasada»** y el robot queda deshabilitado. | Sin una imagen reciente del recuadro, el robot no sabe dónde está. Se deshabilita a propósito. | Cuando vuelva el recuadro verde: **E** y **G**. |
| **El recuadro no se confirma o se pierde** con la cámara en la mano, poca luz o sombras. | El detector de cinta necesita los cuatro lados nítidos y suelo claro a ambos lados de la cinta. | Cámara fija, luz uniforme, cinta sin tapar. |
| **Un residuo empujado saca a otro de la hoja amarilla.** | La hoja es pequeña. | Retira a mano cada residuo en cuanto el panel lo cuente. |
| **Solo funciona en Mac.** | La cámara se lee con AVFoundation, que solo existe en macOS. | En Windows o Linux solo funciona la consola Bluetooth. |

## Instalación

### No encuentra Python o una biblioteca

Usa siempre el Python del proyecto (`work/venv/bin/python`), no otro del sistema. Si aparece `No module named …`, vuelve a instalar las bibliotecas con ese mismo Python (paso 3 de [Instalación](INSTALACION.md)). No copies la carpeta `work/venv` de otro ordenador: créala de nuevo.

### OpenCV no encuentra CSRT

`requirements_vision.txt` instala `opencv-python` y `opencv-contrib-python`, que comparten el mismo módulo y a veces se pisan. Deja solo la variante contrib:

```sh
work/venv/bin/python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless
work/venv/bin/python -m pip install opencv-contrib-python==5.0.0.93
work/venv/bin/python -c "import cv2; print(hasattr(cv2, 'TrackerCSRT_create'))"
```

Debe imprimir `True`. No uses las variantes `headless`: no abren ventanas.

### Los modelos no aparecen al clonar

Es intencionado: los modelos no se suben a GitHub. Los generales se descargan con `work/venv/bin/python outputs/preparar_modelos.py` (necesita Internet, Git y curl). Los propios (`residuos-propio.pt`, `robot-propio.pt`) hay que pedírselos a Juan. Si una descarga se corta, repite el preparador; si un modelo quedó dañado, apártalo y vuelve a descargarlo.

### La ventana dice «Detector no disponible: …»

Falta un modelo general (`residuos-world-small.pt` u otro): sin él no arranca ningún detector, tampoco los propios. Ejecuta `preparar_modelos.py`. El mensaje completo dice qué archivo falta.

## Cámara

### No encuentra la cámara

1. Ejecuta `work/venv/bin/python outputs/vision_linea_robot.py --listar-camaras`.
2. Si el teléfono no aparece: abre Camo Studio y Camo, comprueba que la extensión de cámara de Camo está activada (Ajustes del Sistema → General → Ítems de inicio y extensiones → Extensiones de cámara) y que el cable es de datos.
3. Si aparecen varias cámaras reconocidas, elige una con `--camara camo` (o `samsung`, `lifecam`, o su número).
4. Cierra otros programas que usen la cámara (videollamadas, otro programa del proyecto).
5. Revisa en Ajustes del Sistema → Privacidad y seguridad → Cámara que Terminal tiene permiso.

La cámara del Mac se rechaza siempre, a propósito.

### Imagen negra con el logo de Camo, o el programa se cierra

Camo perdió el teléfono (desconectado, bloqueado o sin batería). Vuelve a conectarlo y abre Camo. Con el robot en marcha, si la imagen no cambia en 0,6 s, el programa lo para. Ten el teléfono cargando durante la demostración: una prueba del 1/11 no llegó a empezar porque se quedó sin batería.

### Aviso de bandas negras o de imagen vertical

Bandas negras: la proporción pedida no coincide con la del teléfono; prueba `--resolucion 1280x720` o `--resolucion 1920x1080` (las bandas podrían confundirse con cinta). Imagen vertical: gira el teléfono a horizontal.

## Recuadro y hojas

### El recuadro no aparece, o dice «Borde conservado»

- Deben verse los **cuatro lados** y las esquinas, con suelo claro a ambos lados de la cinta y una franja exterior.
- Que no haya objetos grandes sobre la cinta. El robot sí puede taparla un poco.
- Evita sombras fuertes y reflejos en la cinta.
- Pulsa `t` para buscarlo de nuevo (sobre todo si se movió la cámara).
- Si se ve el candidato en amarillo pero no se confirma, `b` lo confirma a mano.

### Las hojas no aparecen

- Tienen que estar **dentro del recuadro**, planas y con un color saturado. La roja tiene que verse **casi tan clara como el suelo o más** (la caja roja es más oscura y así no se confunden).
- Necesitan verse en el mismo sitio alrededor de un segundo para confirmarse. Después se recuerdan aunque algo las tape.
- Si las moviste, pulsa `t` (borra recuadro y hojas y los busca de nuevo).
- Sin la hoja de un residuo, el robot lo saca del recuadro en vez de llevarlo a la hoja.

### La hoja roja aparece como «caja»

Con poca luz, la hoja roja y la caja roja tienen casi el mismo color. El programa descarta la detección que coincide con la hoja si no hay nada más oscuro encima. Si sigue pasando, mejora la luz.

## Robot

### No encuentra el robot (no aparece la caja azul «RANGER»)

- Comprueba que `outputs/models/robot-propio.pt` existe y que la línea 7 de la ventana termina en «| robot».
- El robot debe estar dentro del recuadro o junto a él, con las orugas visibles.
- Respaldo: pulsa `r`, arrastra un rectángulo que incluya todo el robot y pulsa Enter.

### La caja azul se va a otro objeto

Al empujar, el seguimiento puede quedarse en el residuo. El detector del robot lo corrige solo en cuanto lo ve con suficiente confianza. Si no se corrige, pulsa `n` (reiniciar todo) o `r`.

### El Bluetooth no encuentra el robot

1. Enciende el robot y comprueba que el módulo Bluetooth está puesto.
2. Activa el Bluetooth del Mac y da permiso de Bluetooth a Terminal.
3. Cierra mBlock, la aplicación del teléfono u otros programas conectados al robot.
4. Ejecuta `work/venv/bin/python outputs/ranger_bluetooth.py --listar`. Si el nombre no es `Makeblock_LE10a56219eb91`, pásalo con `--nombre`.

### Conecta pero no responde

El programa espera la versión `RANGER_READY_V2_20261019`. Si el robot tiene otro programa (por ejemplo, el de fábrica), carga el firmware con `outputs/Actualizar_Ranger.command` ([Operación](OPERACION_V2.md#firmware-v2-qué-es-y-cómo-se-carga)). Prueba primero sin movimiento: `--comando x` y `--comando p`.

### No se mueve aunque pulse las teclas

Comprueba, en este orden:

1. La ventana del vídeo está activa (haz clic en ella) y las teclas en minúscula.
2. Recuadro verde.
3. Caja azul sobre el robot.
4. «Bluetooth conectado» (si no, **C**).
5. «Movimiento: HABILITADO» (si no, **E**).
6. Robot con batería y orugas libres.

Después de Espacio, `t`, `n`, `b`, `r` o de cualquier parada de seguridad hay que volver a pulsar **E** (y **G** para el automático).

### Se para con «el robot no avanza»

Varios pasos hacia delante sin moverse: batería baja, orugas atascadas, o la caja azul no está sobre el robot. Revísalo y pulsa **E** y **G**.

### Se sube encima de un residuo

Pasa sobre todo con latas tumbadas. El robot lo detecta (el residuo aparece detrás de él), retrocede, gira unos 70° y lo intenta desde otro ángulo. Si falla tres veces, lo deja para más tarde.

## Detección

### Un residuo no se detecta

- Comprueba que es uno de los cinco que conoce el detector y que la línea 7 de la ventana dice «modelo propio».
- Acerca la cámara (sin dejar de ver todo el recuadro): en la vista de trabajo los residuos miden solo 20-40 px.
- Mejora la luz; evita reflejos sobre la lata.
- No amontones residuos ni los tengas en la mano.
- Para mirarlo de cerca, usa el zoom (`+`, clic sobre el objeto): no cambia la detección, pero ayuda a ver qué pasa.

### Confunde la botella de plástico con el blanqueador

Si duda entre los dos, el programa elige **blanqueador** a propósito: es peor mandar un químico peligroso a la hoja de reciclables. Una botella de plástico en la hoja roja es el error «seguro».

### Aparecen «objeto por identificar» en amarillo

Solo con los detectores generales encendidos: con `--otros-residuos`, o si falta `residuos-propio.pt`. No se cuentan ni se empujan.

## Conteo y panel

### Un residuo llegó a su hoja y no se contó

- Tiene que haberse visto **fuera de su hoja antes**: un residuo que empieza ya sobre su hoja no cuenta.
- Tiene que quedar con el centro encima de la hoja o con al menos el 40 % de su caja pisándola.
- Si el robot lo tapa, se confirma cuando retrocede y vuelve a verse.
- Reglas completas: [Operación](OPERACION_V2.md#cuándo-cuenta-un-residuo).

### Se contó dos veces

Pasa si alguien lo quita de la hoja, lo deja fuera más de 2 s y lo vuelve a poner: es a propósito. Si fue sin tocarlo, guarda la sesión con `--diagnostico` y revisa `estado.json` (lista `tracks`). Para empezar de cero, cierra y abre el programa: la sesión nueva empieza en 0 y las anteriores se conservan.

### El panel dice «Sin imagen de la cámara» o «Panel desconectado»

- El programa principal está cerrado, o el panel se abrió con `Abrir_Dashboard.command` (ese no tiene cámara).
- Abre `Probar_Robot_Linea.command` y recarga http://127.0.0.1:8765.
- Si al arrancar sale «Dashboard: puerto ocupado», ya hay otro panel abierto en el 8765: ciérralo, o usa `--dashboard-port 8766`.

### «Automatización n8n: SIN RESPUESTA» o «PROGRAMA CERRADO»

- SIN RESPUESTA: n8n no está abierto o el flujo no está publicado. Abre `outputs/n8n/Abrir_n8n.command`. Los residuos pendientes se envían solos cuando n8n responde, mientras el programa siga abierto.
- PROGRAMA CERRADO: el programa de la cámara no está abierto.
- APAGADO: se arrancó con `--sin-n8n`.
- Configuración y errores de Google Sheets: [N8N.md](N8N.md).

## GitHub

### GitHub rechaza archivos grandes

Comprueba que `.gitignore` está presente y que no estás añadiendo a la fuerza modelos, `work/` o capturas. Si un archivo grande ya está en un commit, añadirlo a `.gitignore` no lo quita del historial. No borres los modelos locales para arreglarlo: pide ayuda antes de limpiar el historial.

## Qué incluir al pedir ayuda

- Qué hacías, el comando exacto o el lanzador y el mensaje completo.
- Las 9 líneas de texto de la ventana (una captura sirve).
- Si es posible, una carpeta de diagnóstico: `--diagnostico work/diagnostico` guarda `camara.jpg`, `vista.jpg` y `estado.json` cada segundo.

Revisa las imágenes antes de compartirlas: muestran la casa real.
