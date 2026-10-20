# Sensor físico: requisito anterior pendiente de revisión

El requisito inicial era detener la placa al detectar cinta negra con su seguidor de línea. No llegó a implementarse.

El 19 de octubre el usuario solicitó poder seguir manejando cerca y fuera del recuadro y pitar solo al salir. Por tanto, **no activar automáticamente la parada del sensor** sin revisar primero cómo debe convivir con ese nuevo comportamiento. El firmware V2 no lee el sensor físico.

Pendiente con el robot disponible: identificar modelo/puerto, calibrar negro/fondo y acordar si se usará como aviso o en otro modo explícito. Ver [Operación V2](../docs/OPERACION_V2.md).
