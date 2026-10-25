#!/usr/bin/env sh
# Arranca Eidos en Docker. Uso: ./start.sh [--prototipo | --demo]   (por defecto, la plataforma)
set -e
cd "$(dirname "$0")"
P="--profile prototipo --profile demo"

if ! command -v docker >/dev/null 2>&1; then
  echo "No se encuentra Docker." >&2; exit 1
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker no está en marcha." >&2; exit 1
fi

port=8000
service=plataforma
if [ "$1" = "--prototipo" ] || [ "$1" = "--demo" ]; then
  port=3000
  if [ "$1" = "--demo" ]; then service=eidos-demo; other=eidos; else service=eidos; other=eidos-demo; fi
  # Prototipo y demo usan el mismo puerto: para el otro si estaba en marcha.
  docker compose $P stop "$other" >/dev/null 2>&1 || true
fi
docker compose $P up -d --build "$service"

id=$(docker compose $P ps -q "$service")
printf "Esperando a que Eidos responda..."
status=""
i=0
while [ $i -lt 40 ]; do
  status=$(docker inspect --format '{{.State.Health.Status}}' "$id")
  [ "$status" = "healthy" ] && break
  printf "."
  sleep 2
  i=$((i + 1))
done
echo

if [ "$service" = "plataforma" ] && [ "$status" = "healthy" ]; then
  echo "Construyendo las aplicaciones (eidos build all)..."
  docker compose $P exec -T plataforma eidos build all || true
  docker compose $P exec -T plataforma eidos interventions list
fi

address=$(docker compose $P port "$service" "$port" | sed -e 's/^0\.0\.0\.0/localhost/' -e 's/^127\.0\.0\.1/localhost/')
if [ "$status" = "healthy" ]; then
  echo "Eidos en marcha -> http://$address"
  [ "$service" = "plataforma" ] && echo "Consola de supervisión -> http://$address/console.html"
else
  echo "El contenedor no está sano todavía (estado: $status). Revisa los logs:"
fi
echo "Logs:  docker compose logs -f $service"
echo "Parar: ./stop.sh"
