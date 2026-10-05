# Solución de problemas

[Inicio](../README.md) · [Instalación](INSTALACION.md) · [Uso](USO.md)

## No encuentra Python o una biblioteca

Verifica la instalación y ejecuta siempre el Python de `work/venv`, no otro Python del sistema. En Windows la ruta termina en `Scripts/python.exe`; en Mac/Linux, en `bin/python`. Si aparece `No module named bleak`, instala Bleak con ese mismo intérprete. Si aparece `No module named serial`, el modo USB necesita `pyserial` adicional.

Si una versión fijada no tiene distribución compatible para tu equipo, conserva el mensaje completo de pip. No hay instalación limpia validada en todas las arquitecturas. Para BLE no necesitas instalar requisitos de visión. No copies una carpeta venv de otro equipo para solucionar el problema.

## AVFoundation no existe en Windows/Linux

Es una limitación del código de cámara actual, no un permiso que falte. Usa el controlador BLE; la adaptación de cámara está pendiente. Instalar PyObjC fuera de Mac no resuelve esa dependencia del sistema.

## OpenCV no encuentra CSRT o ArUco

El archivo de requisitos conserva `opencv-python` y `opencv-contrib-python`, que comparten el módulo `cv2` y pueden interferir según el orden de instalación. En el entorno de visión del Mac puedes reparar la instalación dejando únicamente la variante contrib con interfaz gráfica:

```sh
work/venv/bin/python -m pip uninstall -y opencv-python opencv-contrib-python opencv-python-headless opencv-contrib-python-headless
work/venv/bin/python -m pip install opencv-contrib-python==5.0.0.93
work/venv/bin/python -c "import cv2; print(hasattr(cv2, 'TrackerCSRT_create'), hasattr(cv2, 'aruco'))"
```

Deben aparecer dos `True`. Las variantes `headless` no son adecuadas para esta aplicación con ventanas. Si reinstalas todo el archivo de requisitos, vuelve a comprobar las funciones. Esta guía describe la reparación; la actualización de documentación no cambia las dependencias del proyecto.

## No abre la webcam externa

Conecta una única Microsoft LifeCam, cierra otras aplicaciones de vídeo y revisa el permiso Cámara para la aplicación que lanza Python en Ajustes del Sistema. Reinicia la prueba después de cambiar conexiones. El selector rechaza cámaras que no contengan `Microsoft LifeCam` en el nombre, incluida la integrada. Otra webcam requiere adaptar el selector; no basta con enchufarla.

## Solo ve una línea o el borde parpadea

Comprueba que se vean las cuatro esquinas y toda la cinta. Fija la cámara, evita reflejos y usa iluminación uniforme. Ajusta el control `Contraste` si confunde juntas. Pulsa `t` para reiniciar el borde. Una línea confirmada manualmente no encierra una zona; un dibujo retenido tampoco demuestra que la cinta siga visible.

## Todo parece papel, o el papel no aparece

Revisa que utilizas `Detectar_Residuos.command` o `vision_linea_robot.py --solo-vision`, y que los modelos están preparados. Comprueba el mensaje del detector de papel. La versión actual compara el candidato con otros materiales y exige dos reconocimientos; las primeras etiquetas pueden tardar. Se rechazan objetos ambiguos y candidatos de más del 20 % de la imagen. Mejora encuadre y luz, pero no interpretes una ausencia como prueba de que no hay residuo. No existe precisión validada para todos los tipos de papel.

## Los modelos no aparecen al clonar

Es intencional. En Mac ejecuta `work/venv/bin/python outputs/preparar_modelos.py` y luego la misma orden con `--comprobar`. Necesitas Internet, Git, curl y suficiente disco. Si falla la descarga, guarda el error y repite el preparador después de recuperar la conexión. `--comprobar` no garantiza integridad. Si un modelo existente está corrupto, aparta específicamente ese archivo antes de descargarlo otra vez.

## Bluetooth no encuentra el Ranger

Enciende el robot y su módulo, activa BLE en el ordenador, acércalo y desconecta mBlock, teléfono y otros controladores. Usa `--listar`; si el nombre difiere del predeterminado, pásalo con `--nombre`. En Mac revisa el permiso Bluetooth; en Linux, el servicio BlueZ y los permisos D-Bus. La consola BLE no utiliza un puerto COM.

## Conecta pero no responde el receptor

La conexión GATT no basta: el programa espera `RANGER_READY_V1` y `OK`. Verifica el firmware personalizado y el módulo compatible con las características TX/RX documentadas. Restaurar fábrica elimina ese receptor. Cierra otros programas que puedan leer el puerto. Prueba `--comando x` y `--comando p` antes de cualquier movimiento.

## No se mueve aunque pulse las teclas

En visión necesitas límite visible, robot seleccionado con `r`, conexión con `c`, condición segura y habilitación con `e`. Enfoca la ventana y usa minúsculas. Si la cámara se movió, pulsa `n` y repite selección. Los márgenes pueden dejar poco espacio: amplía el recinto antes de reducirlos sin calibración. En consola BLE debes pulsar Enter; allí no se utiliza `e`.

## GitHub vuelve a rechazar archivos grandes

Comprueba que `.gitignore` esté presente y que no se estén agregando modelos, entorno o capturas a la fuerza. Si el archivo ya está dentro de un commit, añadirlo a `.gitignore` no lo elimina del historial. No borres modelos locales ni fuerces una subida para intentar arreglarlo: revisa qué commits contienen los binarios y conserva una copia antes de cualquier limpieza de historial.

## Información útil al reportar un problema

Indica sistema operativo, versión de Python, comando exacto utilizado, mensaje completo, modelo de cámara y si falla cámara, detección o conexión. En Mac puedes generar un diagnóstico en `work/diagnostico` siguiendo el manual. Revisa las imágenes antes de compartirlas, porque muestran tu entorno real.
