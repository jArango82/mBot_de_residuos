# Entrenamiento de los detectores propios

Actualizado: 2 de noviembre de 2026

Documento principal: [Documentación técnica del sistema](DOCUMENTACION_TECNICA.md).

[Inicio](../README.md) · [Uso](USO.md) · [Estado](ESTADO.md) · [Arquitectura](ARQUITECTURA.md)

## Qué es entrenar un detector

Un **detector** es un programa de inteligencia artificial que mira una foto y dibuja una caja alrededor de cada objeto que conoce, con su nombre y una confianza de 0 a 1. Los detectores generales (como YOLO-World o Grounding DINO) reconocen objetos a partir de una descripción en texto («una lata de aluminio»), pero con nuestros residuos concretos, vistos desde arriba y pequeños, se equivocaban mucho.

**Entrenar** es enseñar a un detector con ejemplos:

1. Se toman **fotos** de la escena real, con la misma cámara y el mismo montaje que se usarán después.
2. En cada foto se **etiqueta** dónde está cada objeto: un rectángulo y su nombre.
3. Se separan las fotos en dos grupos: unas **para aprender** y otras **para comprobar**, que el modelo nunca ve mientras aprende. Así se sabe si de verdad reconoce los objetos o solo memorizó las fotos.
4. El ordenador ajusta el modelo durante varias pasadas («épocas») sobre las fotos de aprender.
5. Se mide cuántos objetos encuentra en las fotos de comprobar.

Usamos **YOLO11n**, un modelo pequeño y rápido, y lo entrenamos en la gráfica del Mac.

## Modelos en uso

| Archivo (en `outputs/models/`) | Qué reconoce | Entrenado | Fotos para aprender |
|---|---|---|---|
| `residuos-propio.pt` | Caja de cartón, lata, botella de vidrio, botella de plástico, envase de blanqueador | 1/11 | 959 |
| `robot-propio.pt` | El robot | 28/10 | 591 (454 con robot y 137 sin él) |

Ninguno está en GitHub: hay que pedírselos a Juan ([Instalación](INSTALACION.md)). El programa los usa si existen; `--sin-modelo-propio` y `--sin-modelo-robot` los desactivan, y `--modelo-propio RUTA` y `--modelo-robot RUTA` permiten probar otros.

### Historia

| Versión | Fecha | Clases | Resultado |
|---|---|---|---|
| Primer detector | 26/10 | Caja de cartón, envoltura, papel / servilleta | En una escena fija, las dos cajas y la servilleta se vieron el 100 % del tiempo. Solo conocía esos objetos concretos. |
| Caja y lata | 28/10 | Caja de cartón, lata | En 128 fotos no vistas: 96 % de las cajas y 89 % de las latas (con los detectores generales: 25 % y 21 %). Desde entonces los generales se apagan. |
| Cinco residuos (actual) | 1/11 | Las cinco clases | Ver abajo. |

## Cómo se entrenó el detector de cinco residuos

1. **Fotos.** Dos sesiones nuevas el 1/11: una de 145 fotos (casi todas de cerca, solo 17 con la vista de trabajo) y otra de 417 con la cámara fija viendo todo el recuadro: residuos mezclados y movidos, el blanqueador junto a la botella de plástico, cada residuo sobre su hoja, junto al robot y con poca luz. Se sumaron las sesiones anteriores de cajas y latas. **La vista de trabajo es la que importa**: en ella los residuos miden solo 20-40 px.
2. **Etiquetado semiautomático.** Etiquetar a mano cientos de fotos es lento, así que:
   - Grounding DINO y el modelo anterior **propusieron** cajas. Eran muy ruidosas: llamaban «caja» a la hoja roja y confundían el vidrio con plástico o lata.
   - Una limpieza automática clasificó cada propuesta con CLIP (otro modelo que compara imágenes con descripciones) y el color: turquesa = blanqueador, azul = botella de agua, rojo = caja; las hojas, el suelo, las personas y el robot, «no residuo».
   - Después se **revisaron a mano** los recortes, en hojas numeradas: unas 70 correcciones.
   - Un modelo auxiliar entrenado con lo revisado propuso residuos que se habían quedado sin etiqueta (se añadieron unos 165 tras revisarlos), y una búsqueda por color turquesa encontró 65 blanqueadores más.
3. **Entrenamiento.** YOLO11n partiendo del modelo auxiliar, 35 épocas, fotos de 800 px, giros y volteos aleatorios (la cámara mira desde arriba, así que un residuo puede aparecer en cualquier orientación). Unos 70 minutos en la gráfica del Mac.
4. **Comprobación** con fotos que no se usaron para aprender:

   | Clase | 80 fotos de la vista de trabajo | 128 fotos de días anteriores |
   |---|---|---|
   | Caja de cartón | 100 % | 97 % |
   | Lata | 82-83 % | 94 % |
   | Botella de vidrio | 72-88 % | — |
   | Botella de plástico | 89 % | — |
   | Envase de blanqueador | 96-99 % | — |

   - Las dos cifras dependen de cuánto se exige que la caja dibujada coincida con la etiquetada.
   - **Ninguna confusión entre plástico y blanqueador** en esas fotos.
   - Ojo: las 80 fotos de la vista de trabajo son de la misma sesión que parte de las de aprender (otro momento de la misma grabación). La cifra es optimista.
   - Medida estándar del entrenamiento sobre las 208 fotos de prueba (mAP50, de 0 a 1; más es mejor): 0,918 en total; caja 0,994, lata 0,961, vidrio 0,754, plástico 0,959, blanqueador 0,920 (registro `work/entrenar-residuos-v4.log`).
5. **En vivo** (2/11, unos 15 minutos con el robot): lata vista en el 97 % de las imágenes, plástico 89 %, caja 84 %, blanqueador 80 %, **vidrio 5 %**. El vidrio tumbado se confundía con una lata. Juan decidió no seguir con el vidrio.

Además del modelo, el programa añade reglas ([Arquitectura](ARQUITECTURA.md#el-recorrido-de-una-imagen)): una sola etiqueta por objeto; **si duda entre botella de plástico y blanqueador, elige blanqueador** (peligroso); y sobre su propia hoja acepta menos confianza, porque el fondo de color no aparecía al principio en las fotos.

## Cómo se entrenó el detector del robot

Grounding DINO, que buscaba el robot por una descripción, fallaba con el robot pequeño en la imagen (unos 25 px): elegía la pata de una silla, todo el recuadro o nada. Se entrenó un detector propio en dos vueltas:

1. Etiquetas iniciales a partir de las grabaciones de las pruebas (donde se sabía por dónde iba el robot), afinadas con DINO en un recorte ampliado.
2. Un primer modelo (`robot-v0.pt`) propuso cajas en el resto de fotos; se revisaron a mano las dudosas.
3. Modelo final con 591 fotos para aprender (137 sin robot, para que aprenda lo que no es el robot).

Resultado en 83 fotos no vistas de otra prueba: encontró el robot en **74 de 74** y no inventó ninguno en las 9 sin robot, en unos 11 ms por foto. DINO, en esas mismas fotos, lo encontraba en 1 de 74.

## Tomar fotos nuevas

Hace falta cerrar antes cualquier programa que use la cámara.

1. Monta el teléfono **fijo**, a la misma altura y con el mismo ángulo que con el robot. Debe verse todo el recuadro y una franja exterior.
2. Abre Camo Studio con el teléfono transmitiendo (cámara trasera).
3. Abre `outputs/Recoger_Imagenes.command`. Empieza en automático: **cada 2 segundos toma una foto y suena un aviso**.
4. Entre aviso y aviso, cambia algo: mueve un residuo, gíralo, quita uno, añade otro.
5. Teclas: `Espacio` guarda una foto ya; `a` activa o desactiva el automático; `q` termina.

No se guardan fotos negras ni congeladas (Camo sin teléfono). En automático tampoco las movidas (`--nitidez-min`, por defecto 60). Con `Espacio` se guardan igual, con un aviso.

Desde Terminal, con nombre de sesión y cada 3 s:

```sh
work/venv/bin/python outputs/recoger_imagenes.py --sesion tarde-luz-lampara --auto --cada 3
```

Cada vez se crea una **sesión**: una carpeta en `work/dataset/imagenes/` con la fecha y hora, o con el nombre de `--sesion`.

### Qué fotografiar

Lo aprendido en estas semanas:

- **La vista de trabajo**, no fotos de cerca: de las 145 fotos de la primera sesión del 1/11, solo 17 tenían la vista de trabajo.
- Cada residuo **en distintas zonas** del recuadro, también junto a la cinta, encima de su hoja y encima de la otra hoja.
- **Girado, tumbado, de pie**, junto a otros, tocándose o tapándose un poco, y **junto al robot**.
- Los residuos que se parecen, **juntos** (botella de plástico y blanqueador).
- **Distintas luces**: de día, de noche, con lámpara, con poca luz.
- Alrededor de **una foto de cada diez sin residuos**, para que aprenda qué no es un residuo (suelo, cinta, hojas, robot).
- Al menos 40-50 fotos de cada residuo, en **varias sesiones** distintas (otro día, otra luz): una sesión entera se reserva para comprobar.
- **Sin personas.** Una mano moviendo un objeto no importa, pero no la etiquetes.

## Etiquetas y volver a entrenar

Las etiquetas revisadas de cada sesión se guardan en un archivo JSON, `work/dataset/<carpeta de etiquetas>/<sesión>.json`, con las cajas en píxeles de la foto original:

```json
{"classes": ["caja de carton", "lata"],
 "labels": {"0001.jpg": [{"cls": 0, "box": [120, 80, 180, 150]}]}}
```

Los archivos con un punto más en el nombre (`<sesión>.dino.json`, `.modelo.json`, `.limpio.json`) son **propuestas sin revisar** y no se usan para entrenar. Las herramientas de propuesta y revisión que se usaron (`work/etiquetar_cinco.py`, `work/corregir_cinco.py` y otras) están solo en el Mac de Juan, dentro de `work/`, y no en GitHub. **No hay todavía una herramienta cómoda para etiquetar.**

Para entrenar se usa `outputs/entrenar_detector.py`. Ejemplo con los ajustes del detector actual de cinco residuos:

```sh
work/venv/bin/python outputs/entrenar_detector.py \
  --etiquetas work/dataset/etiquetas-cinco-final \
  --prueba nuevos-vista-b residuos-mov-b empuje-20261027-b \
  --epocas 35 --tam 800 --base outputs/models/residuos5-v0.pt \
  --salida outputs/models/residuos-nuevo.pt
```

| Opción | Qué indica |
|---|---|
| `--prueba` | Sesiones reservadas para comprobar (obligatorio; no se aprende de ellas). |
| `--etiquetas` | Carpeta de etiquetas (por defecto `work/dataset/etiquetas`). |
| `--salida` | Dónde guardar el modelo (por defecto `outputs/models/residuos-propio.pt`: ¡sobrescribe el actual!). |
| `--epocas` | Pasadas de entrenamiento (por defecto 80). |
| `--tam` | Tamaño de las fotos al entrenar (por defecto 960). El programa analiza luego al mismo tamaño. |
| `--base` | Modelo de partida (por defecto `yolo11n.pt`). |

Para el robot: `--etiquetas work/dataset/etiquetas-robot --prueba empuje-20261027-b --salida outputs/models/robot-propio.pt`.

Prueba el modelo nuevo con `--modelo-propio outputs/models/residuos-nuevo.pt` antes de sustituir el actual, y guarda una copia del anterior. Se guarda el modelo de la última época, no el que mejor puntúa en las fotos de comprobación, para no hacer trampa con ellas. Al terminar, el resultado de la comprobación (mAP50 total y por clase) se imprime y se guarda en `work/entrenamientos/<nombre>/resultado.json`.

## Límites

- Solo reconoce **estos residuos concretos** (la caja roja, la caja blanca y azul, la lata, la botella de plástico, el envase de blanqueador y la botella de vidrio de las fotos). Otra marca u otro tamaño puede no reconocerse.
- **La botella de vidrio** apenas se detecta en vivo, sobre todo tumbada. Se decidió no seguir con ella.
- Se equivoca más con residuos **amontonados** (una lata encima de la caja), **en la mano** o con una luz muy distinta.
- Todo se entrenó en la casa de Juan, con su suelo y su luz: en la exposición puede funcionar peor.

## Privacidad

Las fotos se quedan en el Mac, dentro de `work/`, que no se sube a GitHub. Revisa que no aparezcan personas ni documentos antes de compartir alguna. Ningún análisis envía imágenes fuera del Mac.
