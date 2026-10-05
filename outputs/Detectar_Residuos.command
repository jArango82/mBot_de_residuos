#!/bin/zsh
cd -- "${0:A:h}"
../work/venv/bin/python vision_linea_robot.py --solo-vision "$@"
printf '\nPulsa Enter para cerrar.'
read respuesta
