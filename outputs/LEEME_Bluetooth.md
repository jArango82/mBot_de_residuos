# Bluetooth: documentación actual

Consulta [Bluetooth, firmware y scripts propios](../docs/ROBOT.md) para cargar el receptor, enviar letras, utilizar la consola o crear un script. La [guía de instalación](../docs/INSTALACION.md) contiene los comandos específicos para Mac, Windows y Linux y aclara qué plataformas se han probado.

`Iniciar_Bluetooth.command` es un acceso exclusivo de Mac. El controlador `ranger_bluetooth.py` utiliza BLE mediante Bleak y no necesita un puerto serie Bluetooth. El control directo no incorpora protección de cámara ni lee el sensor de línea físico.
