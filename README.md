# mBot de residuos

Prototipo educativo para observar una zona con una webcam, detectar posibles residuos y controlar un **mBot Ranger** mediante letras enviadas por Bluetooth. El objetivo futuro es que recoja residuos sin salir de la zona delimitada con cinta negra.

**Estado al 5 de octubre de 2026:** hay detección visual experimental y control manual del robot. **Todavía no recoge residuos ni navega automáticamente hacia ellos.**

## Qué hay disponible

- Detección automática del recuadro de cinta negra, con reinicio de selección.
- Detección de posibles botellas, latas, vasos, cartón, bolsas, envolturas, papel y otros objetos. Puede equivocarse u omitir residuos.
- Un detector adicional de papel con verificación para reducir falsos positivos.
- Seguimiento del Ranger sin etiqueta impresa: se selecciona una vez con el ratón.
- Control manual por Bluetooth con `w`, `a`, `s`, `d`, parada, luces y buzzer.
- Protección visual experimental que bloquea el movimiento cerca del borde o al perder la visión. Durante este modo los LED se apagan y la alarma usa el buzzer.
- Firmware con parada tras 600 ms sin nuevas órdenes de movimiento.

**Pendiente:** parada con el seguidor de línea físico, adaptación de la cámara a Windows/Linux, navegación, recogida y validación física de la protección del borde. Una detección en pantalla no genera movimientos hacia el residuo.

## Compatibilidad real

- **Mac:** cámara y Bluetooth utilizados en el montaje original. La cámara debe identificarse como Microsoft LifeCam; no se abre la integrada como alternativa.
- **Windows:** instrucciones para control Bluetooth. El código BLE utiliza una biblioteca compatible, pero este proyecto no se ha probado allí. La cámara de esta versión no funciona en Windows.
- **Linux:** instrucciones para control Bluetooth con BlueZ. No probado en este proyecto. La cámara de esta versión no funciona en Linux.

Instalar las dependencias no convierte la aplicación de cámara en multiplataforma: usa AVFoundation, exclusivo de Apple. Consulta las instrucciones de tu sistema antes de instalar.

## Empieza aquí

1. [Instalación en Mac, Windows y Linux](docs/INSTALACION.md): requisitos, comandos y comprobaciones.
2. [Manual de uso](docs/USO.md): residuos, cinta, robot y teclas.
3. [Bluetooth y firmware](docs/ROBOT.md): preparar la placa, enviar órdenes y escribir un script.
4. [Estado y límites](docs/ESTADO.md): qué se verificó y qué falta.
5. [Archivos y funcionamiento interno](docs/ARQUITECTURA.md): qué hace cada parte.
6. [Solución de problemas](docs/PROBLEMAS.md): cámara, modelos, Bluetooth e instalación.

### Inicio rápido en un Mac ya preparado

Desde la carpeta del proyecto:

```sh
work/venv/bin/python outputs/vision_linea_robot.py --solo-vision
```

También puedes abrir `outputs/Detectar_Residuos.command`. No necesita tener el robot conectado. Coloca la LifeCam fija encima de la zona y enfoca los residuos. Pulsa `t` para reiniciar la selección del borde y `q` para salir, con la ventana de cámara enfocada.

## Qué descarga GitHub

El repositorio incluye código, configuración, documentación y proyectos mBlock. **No incluye los modelos grandes, el entorno Python ni las capturas locales.** El programa `outputs/preparar_modelos.py` descarga y prepara los modelos; las instrucciones están en la guía de instalación. Requiere Internet para la preparación inicial; el análisis de imagen se hace localmente.

No copies el entorno `work/venv` de un sistema a otro: créalo de nuevo. No hace falta subir modelos de más de 100 MB para compartir este código. Las licencias de las bibliotecas y modelos de terceros siguen siendo aplicables; consulta sus proyectos originales antes de redistribuirlos o usarlos comercialmente.
