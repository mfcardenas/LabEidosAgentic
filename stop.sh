#!/usr/bin/env sh
# Para Eidos (los datos se conservan en el volumen eidos-data).
set -e
cd "$(dirname "$0")"

docker compose --profile prototipo --profile demo down
echo "Eidos parado. Los datos siguen en el volumen 'eidos-data'."
