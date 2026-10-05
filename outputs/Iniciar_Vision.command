#!/bin/zsh
cd -- "${0:A:h}"
../work/venv/bin/python vision_ranger.py "$@"
printf '\nPulsa Enter para cerrar.'
read respuesta
