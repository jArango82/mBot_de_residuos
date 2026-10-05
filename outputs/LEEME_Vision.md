# Visión: documentación actual

La guía completa está en [Manual de uso](../docs/USO.md), con instalación en [Mac, Windows y Linux](../docs/INSTALACION.md) y [estado actual](../docs/ESTADO.md).

El inicio recomendado en Mac es `Detectar_Residuos.command` para residuos sin robot, o `Probar_Robot_Linea.command` para seleccionar y seguir el Ranger sin etiqueta impresa. `Iniciar_Vision.command` conserva el modo antiguo con etiqueta ArUco.

La captura actual requiere una Microsoft LifeCam y macOS. La detección es experimental; no hay navegación autónoma ni parada con el sensor de línea físico. Durante el control visual se apagan los LED y la alarma utiliza buzzer. Consulta [solución de problemas](../docs/PROBLEMAS.md) si falla cámara, borde o papel.
