# Instalación por sistema operativo

[Volver al README](../README.md) · [Uso](USO.md) · [Problemas](PROBLEMAS.md)

## Antes de empezar

Puedes usar **solo Bluetooth**, sin webcam ni modelos, o **visión en Mac**, con o sin robot. Para Bluetooth necesitas un Ranger encendido, módulo BLE compatible con el protocolo del proyecto y el [firmware receptor](ROBOT.md). No todos los módulos llamados Bluetooth son BLE ni usan las mismas características.

Descarga el repositorio con GitHub Desktop, o con Git:

```sh
git clone https://github.com/jArango82/mBot_de_residuos.git
cd mBot_de_residuos
```

También puedes descargar el ZIP desde GitHub y extraerlo. Abre la terminal dentro de la carpeta que contiene `README.md` y `outputs`. Todos los comandos siguientes parten de esa carpeta. Si la ruta tiene espacios, escríbela entre comillas.

Se utilizó **Python 3.13** en el Mac original. Para el controlador BLE se necesita Python 3.11 o posterior por el uso de `asyncio.timeout`; utiliza 3.13 para seguir estas instrucciones. La instalación completa de visión fuera del equipo original no está validada. Reserva varios GB de disco: solo los modelos superan 1 GB y las bibliotecas ocupan espacio adicional.

## macOS: visión y Bluetooth

Instala Python 3.13 y Git desde sus distribuidores oficiales si no los tienes. El preparador también necesita `curl` en la terminal. Comprueba:

```sh
python3.13 --version
git --version
curl --version
```

Crea un entorno aislado para este proyecto:

```sh
python3.13 -m venv work/venv
work/venv/bin/python -m pip install --upgrade pip
work/venv/bin/python -m pip install -r outputs/requirements_vision.txt
work/venv/bin/python outputs/preparar_modelos.py
work/venv/bin/python outputs/preparar_modelos.py --comprobar
```

Git es necesario también para instalar CLIP, cuya dependencia apunta a un commit de su repositorio. El preparador descarga CLIP, YOLO y Grounding DINO desde sus fuentes oficiales y genera el detector con las categorías del proyecto. No abre la cámara ni conecta el robot. `--comprobar` solo confirma que existen cuatro archivos principales: no valida su contenido ni realiza una prueba de inferencia.

Comprueba las funciones de OpenCV que utiliza el proyecto:

```sh
work/venv/bin/python -c "import cv2; print(cv2.__version__); print('CSRT:', hasattr(cv2, 'TrackerCSRT_create')); print('ArUco:', hasattr(cv2, 'aruco'))"
```

Los dos últimos valores deben ser `True`. Si no lo son, consulta [Problemas](PROBLEMAS.md).

Conecta una única Microsoft LifeCam y ejecuta:

```sh
work/venv/bin/python outputs/vision_linea_robot.py --solo-vision
```

Autoriza el acceso a cámara para la aplicación que ejecuta Python cuando macOS lo solicite. Para Bluetooth autoriza también ese permiso. Cierra otras aplicaciones que estén utilizando la webcam o el robot.

Los accesos `.command` son para macOS, usan zsh y esperan el entorno en `work/venv`. Si Finder no los ejecuta, usa los comandos de Python de esta guía; no hace falta cambiar la seguridad del sistema. Para instalar **solo Bluetooth** puedes omitir toda la instalación de visión y seguir:

```sh
python3.13 -m venv work/venv
work/venv/bin/python -m pip install bleak==3.0.2
work/venv/bin/python outputs/ranger_bluetooth.py --listar
work/venv/bin/python outputs/ranger_bluetooth.py --comando p
```

## Windows: Bluetooth, sin cámara en esta versión

Utiliza Windows 11 con un adaptador BLE y Python 3.13. Estas instrucciones son para **PowerShell**, abierto en la carpeta del proyecto. No se usan los accesos `.command` de Mac ni es necesario activar el entorno o modificar la política de ejecución de PowerShell.

```powershell
py -3.13 --version
py -3.13 -m venv work/venv
.\work\venv\Scripts\python.exe -m pip install --upgrade pip
.\work\venv\Scripts\python.exe -m pip install bleak==3.0.2
.\work\venv\Scripts\python.exe outputs/ranger_bluetooth.py --listar
.\work\venv\Scripts\python.exe outputs/ranger_bluetooth.py --comando p
.\work\venv\Scripts\python.exe outputs/ranger_bluetooth.py
```

Si el robot tiene otro nombre, añade `--nombre "NOMBRE_ENCONTRADO"`. Activa Bluetooth en Windows y desconecta mBlock u otras aplicaciones del robot. La prueba `p` detiene motores y produce un pitido; no envía un movimiento.

**No ejecutes los programas de cámara esperando que funcionen aquí:** importan AVFoundation y usan el selector de dispositivos de Mac. No existe todavía un lanzador de visión para Windows. El control BLE tampoco ha sido probado físicamente en Windows con este montaje.

## Linux: Bluetooth, sin cámara en esta versión

Necesitas Python 3.11 o posterior, el módulo `venv`, un adaptador BLE y el servicio BlueZ. Las versiones y paquetes dependen de tu distribución. Ejemplo para Debian/Ubuntu:

```sh
sudo apt update
sudo apt install python3 python3-venv bluez
python3 --version
bluetoothctl --version
systemctl status bluetooth
```

Comprueba que Python sea al menos 3.11 y BlueZ al menos 5.55. Si tu distribución ofrece versiones anteriores, actualízalas por sus procedimientos oficiales antes de continuar. Si Bluetooth está desactivado, actívalo en la configuración del escritorio. Después, desde la carpeta del proyecto:

```sh
python3 -m venv work/venv
work/venv/bin/python -m pip install --upgrade pip
work/venv/bin/python -m pip install bleak==3.0.2
work/venv/bin/python outputs/ranger_bluetooth.py --listar
work/venv/bin/python outputs/ranger_bluetooth.py --comando p
work/venv/bin/python outputs/ranger_bluetooth.py
```

Añade `--nombre "NOMBRE_ENCONTRADO"` si es necesario. Ejecuta el programa como usuario normal, no con `sudo`. Las políticas de acceso a BlueZ/D-Bus dependen de la distribución; consulta sus permisos si se deniega la conexión. Estos pasos no se han probado físicamente en Linux con este robot.

La visión sigue pendiente en Linux: no basta con instalar OpenCV ni con indicar `/dev/video0`. Hay que adaptar la clase de cámara, la selección explícita de webcam externa y sus comprobaciones. No se proporciona una receta de cámara que el código actual no pueda ejecutar.

## Actualizar o trasladar el proyecto

Usa Pull origin en GitHub Desktop o `git pull` si no tienes cambios locales que entren en conflicto. Si cambian las dependencias, vuelve a instalar el archivo de requisitos en Mac. Ejecuta el preparador si faltan modelos. No borres los modelos para actualizar el código.

En otro ordenador vuelve a crear `work/venv`; las rutas y ejecutables del entorno no son portables. Los modelos se pueden volver a descargar. La opción BLE requiere únicamente Bleak, sin instalar las bibliotecas de visión.

## Referencias de plataforma

Los requisitos de la biblioteca no equivalen a pruebas de este proyecto. Bleak documenta sus plataformas en [su documentación oficial](https://bleak.readthedocs.io/en/develop/contributing.html). Los motores de captura por sistema están descritos en [OpenCV](https://docs.opencv.org/4.5.3/d4/d15/group__videoio__flags__base.html). La restricción actual de la cámara se comprobó directamente en `outputs/vision_ranger.py` y `outputs/camaras_mac.py`.
