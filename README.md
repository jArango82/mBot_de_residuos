# mBot de residuos

Visión local con webcam externa y control Bluetooth del mBot Ranger. La cámara detecta el recuadro de cinta y posibles residuos; la clasificación es experimental y puede equivocarse.

## Instalar en macOS

Requiere Python 3.13 y curl. Desde la carpeta del proyecto:

```sh
python3 -m venv work/venv
work/venv/bin/python -m pip install -r outputs/requirements_vision.txt
work/venv/bin/python outputs/preparar_modelos.py
```

El último paso descarga modelos oficiales (más de 1 GB). No abre la cámara ni conecta el robot. Los modelos, el entorno Python y las capturas de pruebas se conservan localmente y no se suben a GitHub.

Abre `outputs/Detectar_Residuos.command` para usar solo la cámara. Este montaje selecciona la Microsoft LifeCam VX-5000, sin utilizar la cámara integrada del Mac.

- [Instrucciones de visión](outputs/LEEME_Vision.md)
- [Control Bluetooth](outputs/LEEME_Bluetooth.md)
- [Parada con el sensor físico: trabajo pendiente](outputs/Pendiente_Sensor_Linea.md)

La parada mediante el seguidor de línea físico todavía no está implementada. No se ha validado navegación autónoma hacia los residuos.
