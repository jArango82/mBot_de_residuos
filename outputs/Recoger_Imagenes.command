#!/bin/zsh
cd -- "${0:A:h}"
../work/venv/bin/python recoger_imagenes.py --auto "$@"
printf '\nPulsa Enter para cerrar.'
read respuesta
