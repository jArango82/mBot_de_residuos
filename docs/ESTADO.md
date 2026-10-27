# Estado real del proyecto

Fecha de esta documentación: **20 de octubre de 2026**. [Inicio](../README.md)

## Ajuste del 26 de octubre: Samsung como cámara

La selección de cámara acepta, además de la LifeCam, un Samsung Galaxy como cámara web (modo USB o Camo), con `--camara` y `--listar-camaras`; la integrada sigue rechazada. Con el teléfono se capta hasta 1280 px y el análisis se mantiene a 640 px de lado mayor; la imagen original se usa en el zoom y en los detectores del recorte. Se añadió parada si la imagen no cambia con el robot en marcha (cámara virtual congelada), se excluyen los puertos USB del teléfono al buscar el Ranger y los modelos se cargan de uno en uno (antes, una carga simultánea podía dejar el detector general «no disponible»). Después se probó con el teléfono real mediante Camo (el S24 Ultra no ofrece cámara web USB): imagen del recinto a 1280 × 720 y ~30 fps, recuadro seleccionado automáticamente. Se añadieron: marca de agua de Camo ignorada, detector general en la gráfica del Mac a 1280 px, histéresis y voto de etiqueta, prioridad de detecciones concretas sobre «objeto por identificar» y una sola descripción por caja en el detector de papel (antes el papel salía como envoltura). También se corrigió la confusión de cajas y papel con envolturas (alternativa «a cardboard box» y regla de color para objetos arrugados sin color). En una grabación real (caja de cartón, papel arrugado y rollo de cinta, con el teléfono moviéndose), reproducida en tiempo real: caja bien etiquetada en el 78 % de las muestras (antes 21 %), papel en el 40 % (antes 0 %) y muestras con alguna etiqueta errónea en el 30 % (antes 68 %). La envoltura verde real se siguió reconociendo en sus seis variantes de control. Con el teléfono fijo y otra escena (dos cajas de medicamento y una servilleta), se añadió el reconocimiento de cajas pequeñas en el detector de papel, la alternancia con zoom y la permanencia de objetos quietos. La caja naranja pasó del 0 % al 98–100 % de las muestras y la servilleta del 0 % al 61–81 %, sin etiquetas erróneas; la caja blanca y azul sigue sin detectarse. Son escenas pequeñas: no son métricas generales de precisión.

Ese mismo día se entrenó un **detector propio** (YOLO11n) con 91 fotos etiquetadas y revisadas. Se comprobó con 46 fotogramas de otra sesión: mAP50 0,995, y en tiempo real las dos cajas y la servilleta se muestran el 100 % del tiempo. Solo conoce esos objetos concretos y la envoltura no se ha comprobado; ver [Entrenamiento](ENTRENAMIENTO.md). Movimiento del robot con esta cámara: no probado.

## Ajuste del 20 de octubre

Se añadió reconocimiento específico de envolturas pequeñas con giros adaptativos y verificación CLIP. La envoltura del montaje fue detectada en vivo con la cámara inclinada y en seis variantes de una captura (cuatro giros y dos perspectivas simuladas). Se añadieron pruebas de transformación de coordenadas, caducidad y no duplicación. No se garantiza reconocimiento de todos los objetos o vistas.

## Cambios de esta entrega

Implementados: actualizador USB con comprobación de versión, firmware V2 compilado, alarma de salida sin frenado por borde y dashboard con conteo persistente. Robot no disponible: carga y prueba física pendientes. Ver [Operación V2](OPERACION_V2.md). El antiguo requisito del sensor que frene al ver negro queda aplazado para revisar su compatibilidad con el nuevo manejo.

## Objetivo final

Una cámara cenital observa el área de trabajo, ubica residuos y robot, y permite planear su aproximación. El uso futuro del seguidor de línea debe revisarse: ahora el usuario solicita permitir el cruce y avisar. Ese objetivo completo **todavía no está implementado**.

## Implementado

- Cámara externa en Mac (LifeCam a 640 × 480; Samsung/Camo hasta 1280 px, analizado a 640 px), sin recurrir a la integrada.
- Segmentos de cinta y recuadro con selección automática y estabilización.
- Detección abierta de posibles residuos con YOLO-World y detector especial de papel Grounding DINO + CLIP.
- Seguimiento del robot por selección manual inicial CSRT, sin marcador impreso en el modo actual.
- BLE con confirmación de comandos, control de motores, luces y buzzer.
- Pasos manuales permitidos cerca/fuera del borde, aviso al salir y parada silenciosa si se pierde vigilancia; temporizador en firmware.
- Script de descarga de modelos para mantener el repositorio sin binarios grandes.

## Qué se comprobó y qué no

Se utilizó la LifeCam real en macOS. Se corrigió una selección inicial que abría la cámara integrada. Se trabajó con imágenes reales de cinta, botella, papel y un objeto confundido con papel; se añadió verificación para reducir esa confusión. No hay un conjunto de evaluación amplio ni métricas de precisión por categoría.

El 29 de septiembre se cargó el receptor por USB y se verificaron 6626 bytes. El usuario confirmó LED rojos y buzzer. Se obtuvieron respuestas del receptor por BLE y se probó el buzzer; USB seguía conectado para alimentación. No se ha completado una prueba física de desplazamiento ni de frenado junto al borde.

Durante el desarrollo se ejecutaron pruebas locales de geometría, selección de cámara, estabilidad del borde, caducidad de detecciones y orden de comandos. Esos archivos están en el área local `work`, excluida de GitHub; **ahora se incluye `tests/test_operacion.py` con pruebas reproducibles de V2**, sin imágenes privadas. Una comprobación sintética no sustituye la validación del robot real.

La presencia de los modelos se comprobó en el Mac original. La documentación no implica que se haya ensayado una instalación limpia en cada sistema. Windows y Linux no se han probado con este hardware. La biblioteca BLE ofrece soporte para esos sistemas, pero la cámara del proyecto es exclusivamente macOS.

## Límites de interpretación

- Una etiqueta no demuestra que un objeto sea residuo ni identifica con fiabilidad su material. Las botellas se muestran sin distinguir vidrio/plástico.
- El detector puede confundir tapas, superficies y objetos cotidianos, o no reconocer papel. Rechazar casos ambiguos reduce falsos positivos pero también puede omitir residuos.
- El seguimiento del robot puede desviarse, especialmente con reflejos, oclusiones o cambios de iluminación.
- El borde dibujado puede ser una referencia retenida; el estado de visibilidad decide si se permite mover.
- En V2 se permite cruzar la cinta. El aviso se basa en píxeles y puede fallar por errores visuales; no hay bloqueo físico del borde.
- No existe selección automática de objetivo, planificación de ruta, aproximación, recogida ni clasificación física de residuos.

## Próximos trabajos

1. Confirmar el uso futuro del sensor físico antes de implementarlo: el nuevo comportamiento permite cruzar y avisa, por lo que la parada al detectar negro ya no se debe activar implícitamente.
2. Validar movimiento, sentido de motores, alimentación solo con baterías y distancias de parada con el robot disponible.
3. Adaptar la cámara a Windows/Linux conservando selección explícita de webcam externa y detección de pérdida de vídeo; probar en hardware real.
4. Reunir y etiquetar ejemplos reales para medir errores, ajustar categorías o entrenar un detector.
5. Calibrar geometría y orientación, diseñar navegación y mecanismo de recogida; integrar después de validar los límites.
6. Publicar pruebas reproducibles sin capturas privadas y verificar instalación limpia.

El requisito detallado del sensor está en [Pendiente_Sensor_Linea.md](../outputs/Pendiente_Sensor_Linea.md). Las tareas físicas y de navegación indicadas siguen pendientes.
