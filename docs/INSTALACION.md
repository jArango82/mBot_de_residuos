# Instalación

Actualizado: 2 de noviembre de 2026

Documento principal: [Documentación técnica del sistema](DOCUMENTACION_TECNICA.md).

[Inicio](../README.md) · [Uso](USO.md) · [Problemas](PROBLEMAS.md)

El proyecto completo (cámara, detección, robot, panel) **solo funciona en Mac**. En Windows y Linux solo se puede usar la consola Bluetooth del robot, y sin probar.

| Sistema | Qué funciona |
|---|---|
| macOS (probado en un Mac con chip Apple M5) | Todo |
| Windows 11 | Solo la consola Bluetooth ([Robot](ROBOT.md)). Sin probar con el robot. |
| Linux | Solo la consola Bluetooth. Sin probar con el robot. |

## Qué necesitas

| Cosa | Para qué |
|---|---|
| Mac con macOS | Ejecutar el programa. Con chip Apple los detectores van mucho más rápido. |
| Python 3.13, Git y curl | El programa está en Python. Git hace falta para instalar CLIP; curl, para bajar los modelos. |
| Unos 3 GB libres | Los modelos generales ocupan algo más de 1 GB; las bibliotecas, otro tanto. |
| Conexión a Internet | Solo durante la instalación. |
| Teléfono con Camo (se usó un Samsung Galaxy S24 Ultra), o una webcam Microsoft LifeCam | La cámara. Nunca se usa la del Mac. |
| mBot Ranger con el firmware V2 | El robot ([Operación](OPERACION_V2.md#firmware-v2-qué-es-y-cómo-se-carga)). |
| Los dos modelos propios, **pedidos a Juan** | Reconocer los cinco residuos y el robot. No están en GitHub. |
| Cinta aislante negra y dos hojas de papel, amarilla y roja | La escena ([Uso](USO.md#antes-de-empezar-el-montaje)). |
| n8n y una cuenta de Google (opcional) | Apuntar los residuos en Google Sheets ([N8N.md](N8N.md)). |

## macOS, paso a paso

Todos los comandos se escriben en **Terminal**, dentro de la carpeta del proyecto (la que contiene `README.md` y `outputs`). Si la ruta tiene espacios, escríbela entre comillas.

1. **Descarga el proyecto** con GitHub Desktop, o con Git:

   ```sh
   git clone https://github.com/jArango82/mBot_de_residuos.git
   cd mBot_de_residuos
   ```

2. **Comprueba Python, Git y curl.** Si falta alguno, instálalo desde su página oficial.

   ```sh
   python3.13 --version
   git --version
   curl --version
   ```

3. **Crea el entorno de Python** del proyecto (una carpeta `work/venv` con sus propias bibliotecas, sin tocar el resto del Mac) e instala las bibliotecas:

   ```sh
   python3.13 -m venv work/venv
   work/venv/bin/python -m pip install --upgrade pip
   work/venv/bin/python -m pip install -r outputs/requirements_vision.txt
   ```

4. **Descarga los modelos generales** (algo más de 1 GB: YOLO, YOLO-World, CLIP, Grounding DINO y la mejora de imagen). El preparador también genera `residuos-world-small.pt`. No abre la cámara ni conecta el robot.

   ```sh
   work/venv/bin/python outputs/preparar_modelos.py
   work/venv/bin/python outputs/preparar_modelos.py --comprobar
   ```

   `--comprobar` solo mira que los archivos existan; no comprueba que estén bien.

5. **Copia los modelos propios.** Los entrenó Juan con sus fotos y **no están en GitHub**: son archivos pequeños (unos 5,5 MB cada uno), pero el proyecto no sube ningún modelo al repositorio. Pídele estos dos archivos y cópialos en `outputs/models/`:

   | Archivo | Qué reconoce |
   |---|---|
   | `residuos-propio.pt` | Caja de cartón, lata, botella de vidrio, botella de plástico y envase de blanqueador |
   | `robot-propio.pt` | El robot |

   Sin ellos el programa arranca, pero funciona mucho peor (ver [más abajo](#si-falta-algún-modelo)).

6. **Comprueba OpenCV.** El seguimiento del robot necesita la función CSRT:

   ```sh
   work/venv/bin/python -c "import cv2; print(cv2.__version__, hasattr(cv2, 'TrackerCSRT_create'))"
   ```

   Debe terminar en `True`. Si no, ver [Problemas](PROBLEMAS.md#opencv-no-encuentra-csrt).

7. **Ejecuta las pruebas automáticas** (unos 20 s, sin cámara ni robot):

   ```sh
   work/venv/bin/python -m unittest discover -s tests
   ```

   Deben terminar con `Ran 149 tests` y `OK`.

8. **Prepara la cámara.** Instala Camo en el teléfono y Camo Studio en el Mac y activa su extensión de cámara ([Uso](USO.md#cámara-lifecam-o-samsung-galaxy)). Comprueba que el Mac la ve:

   ```sh
   work/venv/bin/python outputs/vision_linea_robot.py --listar-camaras
   ```

9. **Primera prueba sin robot:**

   ```sh
   work/venv/bin/python outputs/vision_linea_robot.py --solo-vision
   ```

   macOS pedirá permiso de **Cámara** (y, con el robot, de **Bluetooth**) para la aplicación desde la que lo abres (Terminal). Acéptalo. La ventana debe mostrar el recuadro y los residuos; el panel, en http://127.0.0.1:8765.

10. **Robot.** Si el robot ya tiene el firmware V2 (el de Juan lo tiene desde el 27/10), no hay que hacer nada. Si no, cárgalo con `outputs/Actualizar_Ranger.command`; necesita **mBlock** instalado en el Mac, porque usa sus herramientas para compilar ([Operación](OPERACION_V2.md#firmware-v2-qué-es-y-cómo-se-carga)). Comprueba la conexión con `work/venv/bin/python outputs/ranger_bluetooth.py --comando p` (debe pitar).

11. **n8n (opcional).** n8n se instala aparte en `work/n8n` (fuera de GitHub) y se abre con `outputs/n8n/Abrir_n8n.command`. Los pasos están en [N8N.md](N8N.md). Sin n8n, todo lo demás funciona igual.

Los archivos `.command` son lanzadores de macOS y esperan el entorno en `work/venv`. Si Finder no deja abrirlos, ejecuta en Terminal el comando equivalente de [Uso](USO.md); no hace falta cambiar la seguridad del Mac.

## Si falta algún modelo

| Falta | Qué pasa |
|---|---|
| `residuos-propio.pt` | Se usan los detectores generales (YOLO-World, Grounding DINO + CLIP). No distinguen botella de vidrio de plástico, no reconocen el envase de blanqueador y se equivocan mucho más. Una «botella» sin hoja se sacaría del recuadro en vez de llevarla a una hoja. |
| `robot-propio.pt` | El robot lo busca Grounding DINO cada dos análisis (más de 1 s cada uno, en el procesador). Con el robot pequeño en la imagen falla a menudo; queda `R` para elegirlo con el ratón. |
| `residuos-world-small.pt` u otro modelo general | El panel de la ventana dice «Detector no disponible»: sin ese archivo no arranca ningún detector, tampoco los propios. Vuelve a ejecutar `preparar_modelos.py`. |
| `superres/FSRCNN_x2.pb` | Solo falta la mejora de imagen del zoom; todo lo demás funciona. |

## Windows: solo Bluetooth

Con Windows 11, un adaptador Bluetooth de bajo consumo (BLE) y Python 3.13, en **PowerShell** dentro de la carpeta del proyecto:

```powershell
py -3.13 --version
py -3.13 -m venv work/venv
.\work\venv\Scripts\python.exe -m pip install --upgrade pip
.\work\venv\Scripts\python.exe -m pip install bleak==3.0.2 pyserial==3.5
.\work\venv\Scripts\python.exe outputs/ranger_bluetooth.py --listar
.\work\venv\Scripts\python.exe outputs/ranger_bluetooth.py --comando p
.\work\venv\Scripts\python.exe outputs/ranger_bluetooth.py
```

Activa el Bluetooth de Windows y cierra mBlock u otros programas conectados al robot. Si el robot tiene otro nombre, añade `--nombre "NOMBRE_ENCONTRADO"`. **No ejecutes los programas de cámara en Windows**: usan AVFoundation, que solo existe en Mac.

## Linux: solo Bluetooth

Necesitas Python 3.11 o posterior, el módulo `venv`, un adaptador BLE y el servicio BlueZ (5.55 o posterior). Ejemplo en Debian o Ubuntu:

```sh
sudo apt update
sudo apt install python3 python3-venv bluez
python3 --version
bluetoothctl --version
```

Después, en la carpeta del proyecto y como usuario normal (sin `sudo`):

```sh
python3 -m venv work/venv
work/venv/bin/python -m pip install --upgrade pip
work/venv/bin/python -m pip install bleak==3.0.2 pyserial==3.5
work/venv/bin/python outputs/ranger_bluetooth.py --listar
work/venv/bin/python outputs/ranger_bluetooth.py --comando p
```

Si se deniega la conexión, revisa los permisos de BlueZ de tu distribución. La cámara no funciona en Linux: habría que adaptar el código de cámara, no basta con instalar OpenCV.

## Actualizar o llevar el proyecto a otro Mac

- Para traer cambios: «Pull origin» en GitHub Desktop o `git pull`.
- Si cambió `requirements_vision.txt`, vuelve a ejecutar el paso 3.
- No borres los modelos para actualizar: Git no los toca.
- En otro Mac, crea de nuevo `work/venv` (no se puede copiar de un ordenador a otro), vuelve a descargar los modelos generales y copia los dos modelos propios.
- `work/` no se sube a GitHub: fotos, grabaciones, la base de datos del conteo y n8n se quedan en el Mac donde se crearon. Una copia del repositorio no es una copia de seguridad de esos archivos.
