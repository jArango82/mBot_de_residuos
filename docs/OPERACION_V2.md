# Operación V2: actualización, aviso de salida y conteo

Actualizado el **19 de octubre de 2026**. Esta guía sustituye las instrucciones de frenado por proximidad de la versión anterior.

## Preparar la placa cuando vuelvas a tener el Ranger

En el Mac original ya se compiló el firmware nuevo, pero **no se cargó en el robot**, que no estaba disponible. Debe actualizarse antes de usar la nueva aplicación: el firmware antiguo detenía los motores al pitar.

1. Cierra mBlock y otras aplicaciones que usen USB/Bluetooth del robot.
2. Abre `outputs/Actualizar_Ranger.command`. Esperará a que conectes el Ranger por USB.
3. Conecta el cable. El programa reconoce el receptor anterior, compila la fuente actual, carga y verifica memoria y respuesta de versión.
4. Espera `Actualización verificada: RANGER_READY_V2_20261019`. Deja USB conectado hasta recibir esa confirmación.
5. Enciende las baterías para trabajar después sin USB. Abre `Probar_Robot_Linea.command`, selecciona el cuerpo con `r`, conecta con `c` y habilita con `e`.

También puedes ejecutarlo desde la raíz del proyecto:

```sh
work/venv/bin/python outputs/actualizar_ranger.py --esperar
```

Al conectar desde la aplicación o consola BLE se intenta actualizar primero si hay un único puerto USB disponible. Si no hay USB, se exige la versión V2 por Bluetooth; **BLE no permite cargar este programa de la placa**. Una versión antigua produce un mensaje solicitando USB en vez de aceptar movimientos con un protocolo incompatible. Si ya está actualizada, no se vuelve a escribir la memoria.

Con varios puertos USB serie debes elegir explícitamente el del Ranger:

```sh
work/venv/bin/python outputs/actualizar_ranger.py --puerto /dev/cu.PUERTO_REAL
```

La carga automática exige respuesta de un Ranger V1 o V2: no carga sobre un dispositivo que no identifica. Para una placa con firmware de fábrica, confirma personalmente puerto/modelo y usa `--puerto ... --carga-inicial`. Esta opción permite la primera carga sin identificación previa. No conectes otros equipos serie durante la actualización automática.

El compilador utiliza las herramientas AVR y biblioteca Auriga instaladas por mBlock en el Mac original. `--toolchain RUTA` permite indicar otra carpeta de esas herramientas; no garantiza portabilidad de ejecutables entre sistemas. La compilación/carga automática en Windows/Linux sigue sin validarse. `--compilar` prepara el archivo sin conectar hardware. El archivo `.mblock` también quedó sincronizado con la fuente V2.

## Manejo y alarma

El Ranger sigue aceptando `w/a/s/d` cuando está cerca del borde **y cuando lo cruza**. No se aplica una reserva de frenado por distancia. El buzzer se activa cuando la caja observada del cuerpo sobrepasa más de 5 píxeles algún lado durante al menos 0.25 segundos con imágenes distintas. Es una tolerancia contra vibración de la detección, no una distancia física calibrada.

El aviso `p` de V2 es no bloqueante y **no detiene motores**. Se repite aproximadamente cada dos segundos mientras permanezca fuera. No hay pitido al acercarse, al encender esta versión, por no seleccionar robot ni por perder el borde. Los LED arrancan apagados y la visión los mantiene apagados.

Se mantienen la parada explícita con espacio/`x`, el límite de duración de cada paso, la parada silenciosa al perder imagen/seguimiento/borde y el temporizador de la placa de 600 ms sin nuevas órdenes. Para recuperar pasos tras pérdida de visión, vuelve a seleccionar/habilitar. El controlador directo BLE no usa cámara.

El sensor físico de línea no se activa en esta versión. Su anterior requisito de frenar al ver cinta queda aplazado y debe revisarse antes de implementarlo, para no contradecir el manejo solicitado ahora.

## Abrir el dashboard

Abre `outputs/Abrir_Dashboard.command` y visita **http://127.0.0.1:8765**. También se puede iniciar así:

```sh
work/venv/bin/python outputs/dashboard.py
```

El programa principal de cámara intenta abrir el servidor en ese mismo puerto; si ya está abierto, ambos comparten la base de datos. El servidor es local, de solo lectura y no tiene controles remotos de motores. No publica imágenes ni registros en Internet.

Para empezar a medir sin robot:

```sh
work/venv/bin/python outputs/vision_linea_robot.py --solo-vision
```

Para el robot: omite `--solo-vision`, o abre `Probar_Robot_Linea.command`. Los accesos `Iniciar_Vision.command` y `Probar_Robot_Linea.command` abren ahora el modo actual sin etiqueta. Deja la cámara fija y muestra todo el recuadro **más una franja exterior**, para poder observar los residuos después de salir.

El dashboard incluye total de la sesión, categorías separadas, residuos actualmente visibles dentro, histórico acumulado, gráfico temporal, distribución por categoría, mapa de la sesión activa, últimos eventos, selector de sesiones y exportación CSV. Los estados vacíos muestran cero: no contiene estadísticas inventadas. El mapa siempre representa la sesión activa, incluso si consultas estadísticas históricas.

Los datos quedan en `work/estadisticas.sqlite3`, fuera de GitHub. La exportación contiene sesión, identificador de trayectoria, categoría, fecha UTC y puntuación del detector. La interfaz muestra la hora local del navegador. Al reiniciar la cámara comienza una sesión nueva; el histórico se conserva. No se estima peso, tasa real de reciclaje ni eficiencia sin datos que los respalden.

Para otro puerto usa `dashboard.py --puerto 8766` o `vision_linea_robot.py --dashboard-port 8766`. `--sin-dashboard` mantiene el registro de datos pero no abre servidor. El panel puede funcionar sin robot o sin una sesión de cámara activa.

## Regla de separación

Se sigue la trayectoria de cada objeto por posición y categoría. Debe observarse dentro del recinto en al menos dos resultados nuevos durante 0.35 s y después quedar **su caja completamente fuera** en al menos dos resultados nuevos durante 0.35 s. Una sola línea no habilita conteo: hace falta recuadro completo y visible.

No suma si aparece ya afuera, desaparece, se pierde el borde, cambia la zona o se pierde demasiado tiempo su identidad. Repetir en pantalla el mismo resultado del detector no lo convierte en varios reconocimientos. Los casos de dos objetos cercanos con asociación ambigua se descartan para no inventar una trayectoria.

Cada trayectoria cuenta una sola vez por sesión, incluso si vuelve a entrar mientras siga identificada. No es reconocimiento permanente del objeto: tras una pérdida prolongada o entre sesiones puede recibir otro identificador. Objetos que se ocultan debajo del robot, cambios de categoría, residuos juntos y detecciones erróneas pueden provocar omisiones o conteos incorrectos. La configuración retiene trayectorias seis segundos, pero no valida salidas tras huecos de observación superiores a 2.5 s (4 s para papel y envolturas).

Se cuenta la salida visual, tanto si el residuo lo empuja el robot como si se retira a mano. No se demuestra automáticamente quién lo movió, ni se ha añadido navegación o recogida autónoma.

## Verificación y siguiente prueba real

El firmware compila y las pruebas reproducibles cubren conteo, no duplicación de una trayectoria, persistencia, HTTP/CSV, movimiento cerca/fuera, aviso sin frenar, pérdida de visión silenciosa y actualización simulada. Ejecuta:

```sh
work/venv/bin/python -m unittest discover -s tests -v
```

La primera prueba física sigue pendiente. Una vez actualizado, empieza por `x` y `p`, comprueba que el aviso no bloquea los pasos, acerca/cruza el borde con supervisión y saca un residuo visible. Comprueba un incremento en el panel, permanencia sin nuevos incrementos y exportación. Repite con cada categoría y registra los errores; las pruebas simuladas no validan por sí mismas la clasificación ni el movimiento real.
