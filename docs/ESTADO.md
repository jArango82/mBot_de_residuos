# Estado real del proyecto

Fecha de esta documentación: **5 de octubre de 2026**. [Inicio](../README.md)

## Objetivo final

Una cámara cenital observa el área de trabajo, ubica residuos y robot, y permite planear su aproximación. El seguidor de línea del Ranger debe detenerlo al encontrar cinta negra directamente desde la placa. Ese objetivo completo **todavía no está implementado**.

## Implementado

- Cámara LifeCam externa en Mac, captura a 640 × 480 solicitada, sin recurrir a la integrada.
- Segmentos de cinta y recuadro con selección automática y estabilización.
- Detección abierta de posibles residuos con YOLO-World y detector especial de papel Grounding DINO + CLIP.
- Seguimiento del robot por selección manual inicial CSRT, sin marcador impreso en el modo actual.
- BLE con confirmación de comandos, control de motores, luces y buzzer.
- Bloqueo visual de pasos manuales, supervisión de actualización de imagen y temporizador de parada en firmware.
- Script de descarga de modelos para mantener el repositorio sin binarios grandes.

## Qué se comprobó y qué no

Se utilizó la LifeCam real en macOS. Se corrigió una selección inicial que abría la cámara integrada. Se trabajó con imágenes reales de cinta, botella, papel y un objeto confundido con papel; se añadió verificación para reducir esa confusión. No hay un conjunto de evaluación amplio ni métricas de precisión por categoría.

El 29 de septiembre se cargó el receptor por USB y se verificaron 6626 bytes. El usuario confirmó LED rojos y buzzer. Se obtuvieron respuestas del receptor por BLE y se probó el buzzer; USB seguía conectado para alimentación. No se ha completado una prueba física de desplazamiento ni de frenado junto al borde.

Durante el desarrollo se ejecutaron pruebas locales de geometría, selección de cámara, estabilidad del borde, caducidad de detecciones y orden de comandos. Esos archivos están en el área local `work`, excluida de GitHub; **el repositorio publicado no incluye actualmente una suite de pruebas reproducible**. Una comprobación sintética no sustituye la validación del robot real.

La presencia de los modelos se comprobó en el Mac original. La documentación no implica que se haya ensayado una instalación limpia en cada sistema. Windows y Linux no se han probado con este hardware. La biblioteca BLE ofrece soporte para esos sistemas, pero la cámara del proyecto es exclusivamente macOS.

## Límites de interpretación

- Una etiqueta no demuestra que un objeto sea residuo ni identifica con fiabilidad su material. Las botellas se muestran sin distinguir vidrio/plástico.
- El detector puede confundir tapas, superficies y objetos cotidianos, o no reconocer papel. Rechazar casos ambiguos reduce falsos positivos pero también puede omitir residuos.
- El seguimiento del robot puede desviarse, especialmente con reflejos, oclusiones o cambios de iluminación.
- El borde dibujado puede ser una referencia retenida; el estado de visibilidad decide si se permite mover.
- Los márgenes están en píxeles y no se calibraron con velocidad/frenado reales. No se garantiza que el robot nunca cruce la cinta.
- No existe selección automática de objetivo, planificación de ruta, aproximación, recogida ni clasificación física de residuos.

## Próximos trabajos

1. Confirmar modelo y puerto del seguidor de línea; implementar parada en la placa cuando cualquiera de sus detectores vea negro. Nuevas letras de movimiento no deben anularla mientras persista la condición. Definir retirada y rearme.
2. Validar movimiento, sentido de motores, alimentación solo con baterías y distancias de parada con el robot disponible.
3. Adaptar la cámara a Windows/Linux conservando selección explícita de webcam externa y detección de pérdida de vídeo; probar en hardware real.
4. Reunir y etiquetar ejemplos reales para medir errores, ajustar categorías o entrenar un detector.
5. Calibrar geometría y orientación, diseñar navegación y mecanismo de recogida; integrar después de validar los límites.
6. Publicar pruebas reproducibles sin capturas privadas y verificar instalación limpia.

El requisito detallado del sensor está en [Pendiente_Sensor_Linea.md](../outputs/Pendiente_Sensor_Linea.md). Esta actualización documenta el estado; no implementa esas tareas.
