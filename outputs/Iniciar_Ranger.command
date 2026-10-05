#!/bin/zsh
cd -- "${0:A:h}"
../work/venv/bin/python ranger.py "$@"
printf '\nPulsa Enter para cerrar.'
read respuesta
