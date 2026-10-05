# Archivos y funcionamiento

[Inicio](../README.md) · [Estado](ESTADO.md)

## Flujo general

La LifeCam entrega imágenes a la clase `Camera`. El programa principal detecta la cinta y sigue el cuerpo del robot. En paralelo se ejecutan los detectores de objetos y papel para que la inferencia no detenga la vigilancia del borde. Los objetos se muestran en pantalla; no alimentan un navegador autónomo.

Cuando el usuario solicita un paso y la geometría lo permite, `BluetoothGuard` envía letras al receptor del Ranger. Si la imagen pierde frescura o el estado deja de permitir movimiento, el controlador solicita parada. La placa mantiene además su temporizador independiente por ausencia de órdenes.

## Aplicaciones y accesos

Todos los archivos siguientes están en `outputs/`:

- `vision_linea_robot.py`: aplicación actual de residuos, borde y robot sin etiqueta; `--solo-vision` desactiva conexión al robot.
- `Detectar_Residuos.command`: abre el programa anterior con `--solo-vision`.
- `Probar_Robot_Linea.command`: abre el mismo programa con controles del robot disponibles.
- `vision_linea.py` y `Detectar_Linea.command`: prueba de segmentos negros, sin Bluetooth.
- `vision_ranger.py` y `Iniciar_Vision.command`: aplicación anterior con ArUco y YOLO11n. El módulo también contiene componentes compartidos de cámara, detección y control BLE utilizados por la aplicación actual.
- `ranger_bluetooth.py` y `Iniciar_Bluetooth.command`: consola BLE y clase reutilizable `RangerBluetooth`.
- `ranger.py` y `Iniciar_Ranger.command`: consola USB histórica, dependencia adicional `pyserial`.

Los `.command` son accesos de macOS, no ejecutables de Windows/Linux.

## Módulos internos

- `camaras_mac.py`: enumera dispositivos AVFoundation en el orden de OpenCV y exige una LifeCam externa.
- `vision_core.py`: detección geométrica de líneas/recuadros, ArUco y cálculos de protección.
- `vision_boundary.py`: estabilización, confirmación y seguimiento de evidencia del borde; ajuste de imagen oscura.
- `vision_residuos.py`: agrupación de etiquetas y persistencia temporal de cajas. Las detecciones normales toleran interrupciones de hasta 0.7 s.
- `vision_papel.py`: Grounding DINO Tiny, verificación CLIP y seguimiento de papel entre análisis. Descarta candidatos de más del 20 % de la imagen; requiere dos observaciones verificadas. El seguimiento caduca tras cuatro segundos sin reconocimiento nuevo.

## Modelos y configuración

- `models/residuos-categorias.json`: 24 descripciones en inglés y sus etiquetas en español; varias se agrupan bajo el mismo nombre. El papel de la aplicación actual se muestra mediante su detector dedicado, no por aceptar directamente las etiquetas de papel de YOLO.
- `models/residuos-world-small.pt`: detector predeterminado, generado a partir de YOLO-World-S y las descripciones configuradas.
- `models/yolov8s-worldv2.pt`: base descargada para prepararlo.
- `models/yolo11n.pt`: detector del modo antiguo, con clases COCO.
- `models/clip/ViT-B-32.pt`: codificador utilizado en preparación y verificación de papel.
- `models/grounding-dino-tiny/`: pesos y archivos de configuración/tokenización del detector de papel. Los JSON y vocabulario se versionan; los pesos no.
- `preparar_modelos.py`: descarga a archivos `.partial`, verifica el hash de CLIP y genera `residuos-world-small.pt`. Reutiliza archivos existentes; para los otros modelos no hace validación criptográfica de contenido. La revisión de DINO y el commit de CLIP están fijados en código/requisitos.
- `requirements_vision.txt`: versiones de dependencias usadas; PyObjC solo se instala en macOS. Instalar este archivo en otro sistema no adapta la captura.

Cambiar `residuos-categorias.json` no reentrena un modelo con fotografías. Al volver a ejecutar el preparador se generan características de texto para esas categorías y se sobrescribe el modelo pequeño personalizado. El detector de papel tiene su propia lógica y no se reconfigura únicamente editando ese JSON.

## Firmware y material de referencia

- `ranger_bluetooth.ino`: receptor actual para la placa Auriga, protocolo ASCII y parada temporizada.
- `ranger-bluetooth.mblock`: proyecto de mBlock preparado para ese receptor.
- `ranger_usb.ino`: receptor del modo USB conservado.
- `ranger-original.ino` y `ranger-original.mblock`: respaldo del programa anterior.
- `Etiqueta_Ranger.png`: marcador del modo antiguo; no es necesario en el modo actual.
- `LEEME_Vision.md`, `LEEME_Bluetooth.md`: accesos a los manuales actualizados.
- `Pendiente_Sensor_Linea.md`: requisito aún no implementado del sensor físico.

## Carpetas locales y GitHub

`work/` contiene el entorno Python, cachés, pruebas y diagnósticos del equipo original. `weights/` y los binarios de modelos también están excluidos. `.gitignore` evita subirlos; `.gitattributes` normaliza finales de línea de archivos de texto. No se utiliza Git LFS en la configuración publicada.

Los análisis de cámara se realizan localmente. La instalación sí accede a Internet para paquetes y modelos. Solo se escriben capturas de diagnóstico cuando se solicita esa opción; utiliza una ruta dentro de `work/` para mantenerlas fuera de GitHub. Una copia del repositorio no es un respaldo de esos archivos locales.
