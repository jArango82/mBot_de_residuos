# mBot de residuos

Prototipo de **robot que separa residuos de forma autónoma**. Una cámara mira desde arriba una zona marcada con cinta negra. El programa reconoce cada residuo con inteligencia artificial entrenada con fotos propias, y un **mBot Ranger** lleva cada uno a su hoja de color:

- **Hoja amarilla (aprovechables):** caja de cartón, lata, botella de vidrio y botella de plástico.
- **Hoja roja (peligrosos):** envase de blanqueador.

Un panel web cuenta cada residuo separado y muestra la cámara en vivo. Además, **n8n** apunta cada separación en Google Sheets y responde al panel.

**Estado al 2 de noviembre de 2026:** funciona de punta a punta y está probado con el robot real. El robot llevó el envase de blanqueador a la hoja roja y la caja a la amarilla, y el panel los contó. n8n los apuntó en Google Sheets y respondió al panel. Es un prototipo y tiene límites conocidos: consulta [Estado](docs/ESTADO.md) y [Problemas conocidos](docs/PROBLEMAS.md).

![El robot separando residuos: inicio, empuje y final](docs/imagenes/secuencia_separacion.jpg)

## Empieza aquí

1. **[Guía de estudio](docs/GUIA_DE_ESTUDIO.md):** qué es, cómo funciona paso a paso, qué se hizo, resultados, límites, preguntas del profesor y glosario. **Léela primero.**
2. [Manual de uso](docs/USO.md): teclas, panel y demostración.
3. [Instalación](docs/INSTALACION.md): requisitos y modelos.
4. [Automatización con n8n](docs/N8N.md): Google Sheets y respuesta al panel.
5. [Robot, Bluetooth y firmware](docs/ROBOT.md).
6. [Arquitectura](docs/ARQUITECTURA.md): qué hace cada archivo.
7. [Entrenamiento del detector](docs/ENTRENAMIENTO.md).
8. [Estado](docs/ESTADO.md) y [problemas conocidos](docs/PROBLEMAS.md).

También hay un PDF con todo: [docs/mBot_de_residuos_documentacion.pdf](docs/mBot_de_residuos_documentacion.pdf).

## Uso rápido (en el Mac del proyecto)

1. Doble clic en `outputs/n8n/Abrir_n8n.command` (n8n en http://localhost:5678).
2. Doble clic en `outputs/Probar_Robot_Linea.command` (programa principal).
3. Abrir el panel: http://127.0.0.1:8765.
4. En la ventana del programa: **C** conectar el robot, **E** habilitar, **G** separar residuos, **Espacio** parar.

## Requisitos importantes

- **Solo Mac** (la cámara se lee con AVFoundation, de Apple). Probado en un Mac con chip M5.
- Cámara externa: Samsung con Camo (o LifeCam). La cámara integrada del Mac no se usa nunca.
- Los **modelos entrenados** (`outputs/models/*.pt`) no están en GitHub porque pesan mucho. Los propios (`residuos-propio.pt`, `robot-propio.pt`) hay que pedirlos al autor; los generales se descargan con `outputs/preparar_modelos.py`.
- Pruebas automáticas: `work/venv/bin/python -m unittest discover -s tests` (149 pruebas).
