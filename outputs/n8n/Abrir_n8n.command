#!/bin/zsh
# Abre n8n en este Mac (http://localhost:5678) para apuntar cada residuo separado en Google Sheets.
# n8n está instalado en work/n8n (fuera de Git) y guarda sus datos en work/n8n/datos.
cd "$(dirname "$0")/../.."
export N8N_USER_FOLDER="$PWD/work/n8n/datos"
export N8N_PORT=5678
# Solo desde este Mac. Así se puede quitar la cookie segura, que Safari no acepta en http://localhost.
export N8N_LISTEN_ADDRESS=127.0.0.1
export N8N_SECURE_COOKIE=false
export GENERIC_TIMEZONE="$(readlink /etc/localtime | sed 's|.*/zoneinfo/||')"
export N8N_DIAGNOSTICS_ENABLED=false
export N8N_PERSONALIZATION_ENABLED=false
echo "Abriendo n8n en http://localhost:5678 (Ctrl+C para cerrarlo)"
exec work/n8n/node_modules/.bin/n8n start
