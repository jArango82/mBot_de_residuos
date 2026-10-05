# Requisito acordado para cuando esté disponible el Ranger

El seguidor de línea físico del robot debe detectar la cinta negra y detener los motores directamente desde el programa de la placa, sin depender de la webcam, el Mac o Bluetooth. La webcam se encargará de localizar la zona, el robot y los posibles residuos.

Pendiente de implementar y probar con el robot disponible: confirmar modelo y puerto del sensor, calibrar negro/fondo, comprobar que cualquiera de sus detectores provoque parada, e impedir que nuevos comandos de movimiento anulen esa parada mientras siga detectando la cinta. Definir cómo retirar o rearmar el robot de forma controlada. Conservar el buzzer como aviso y el anillo LED apagado durante la visión.

Este requisito queda registrado para después; el firmware actual todavía no lee ese sensor.
