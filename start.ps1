<#
.SYNOPSIS
  Arranca Eidos en Docker. Por defecto, la plataforma (http://localhost:8000).
.PARAMETER Prototipo
  Prototipo F0 (Node) en http://localhost:3000, en lugar de la plataforma.
.PARAMETER Demo
  Prototipo F0 con el modelo simulado.
.PARAMETER SinConstruir
  No ejecuta `eidos build all` al arrancar la plataforma.
#>
param([switch]$Prototipo, [switch]$Demo, [switch]$SinConstruir)

Set-Location -Path $PSScriptRoot
$profiles = @("--profile", "prototipo", "--profile", "demo")

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Write-Host "No se encuentra Docker. Instala Docker Desktop: https://www.docker.com/products/docker-desktop" -ForegroundColor Red
  exit 1
}
docker info --format '{{.ServerVersion}}' 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
  Write-Host "Docker no esta en marcha. Abre Docker Desktop y vuelve a intentarlo." -ForegroundColor Red
  exit 1
}

if ($Prototipo -or $Demo) {
  if ($Demo) { $service = "eidos-demo"; $other = "eidos" } else { $service = "eidos"; $other = "eidos-demo" }
  $port = 3000
  # Prototipo y demo usan el mismo puerto: para el otro si estaba en marcha.
  docker compose @profiles stop $other 2>$null | Out-Null
} else {
  $service = "plataforma"; $port = 8000
}

docker compose @profiles up -d --build $service
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo arrancar el contenedor." -ForegroundColor Red; exit 1 }

$id = (docker compose @profiles ps -q $service).Trim()
Write-Host "Esperando a que Eidos responda..." -NoNewline
$status = ""
for ($i = 0; $i -lt 40; $i++) {
  $status = (docker inspect --format '{{.State.Health.Status}}' $id).Trim()
  if ($status -eq "healthy") { break }
  Write-Host "." -NoNewline
  Start-Sleep -Seconds 2
}
Write-Host ""

if ($service -eq "plataforma" -and $status -eq "healthy" -and -not $SinConstruir) {
  Write-Host "Construyendo las aplicaciones (eidos build all)..."
  docker compose @profiles exec -T plataforma eidos build all
  docker compose @profiles exec -T plataforma eidos interventions list
}

$address = (docker compose @profiles port $service $port).Trim() -replace '^0\.0\.0\.0', 'localhost' -replace '^127\.0\.0\.1', 'localhost'
if ($status -eq "healthy") {
  Write-Host "Eidos en marcha -> http://$address" -ForegroundColor Green
  if ($service -eq "plataforma") { Write-Host "Consola de supervision -> http://$address/console.html" -ForegroundColor Green }
} else {
  Write-Host "El contenedor no esta sano todavia (estado: $status). Revisa los logs:" -ForegroundColor Yellow
}
Write-Host "Logs:  docker compose logs -f $service"
Write-Host "Parar: .\stop.ps1"
exit 0
