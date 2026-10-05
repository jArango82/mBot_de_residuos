#!/bin/zsh
cd -- "${0:A:h}"
../work/venv/bin/python ranger_bluetooth.py "$@"
printf '\nPulsa Enter para cerrar.'
read respuesta
