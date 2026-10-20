#!/bin/zsh
cd -- "${0:A:h}"
../work/venv/bin/python actualizar_ranger.py --esperar
printf "\nPulsa Enter para cerrar."
read respuesta
