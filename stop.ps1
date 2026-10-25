<#
.SYNOPSIS
  Para Eidos (los datos se conservan en el volumen eidos-data).
#>
Set-Location -Path $PSScriptRoot

docker compose --profile prototipo --profile demo down
if ($LASTEXITCODE -ne 0) { Write-Host "No se pudo parar Eidos." -ForegroundColor Red; exit 1 }
Write-Host "Eidos parado. Los datos siguen en los volúmenes 'eidos-data' y 'eidos-platform-data'." -ForegroundColor Green
