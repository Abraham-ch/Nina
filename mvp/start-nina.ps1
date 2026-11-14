param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$ninaPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ninaPython)) { throw 'Primero ejecuta setup-nina.ps1 para instalar las dependencias.' }
if (-not (Test-Path -LiteralPath 'web\dist\index.html')) { throw 'Falta compilar la interfaz: cd web; npm.cmd ci; npm.cmd run build' }
Write-Host "NINA: http://127.0.0.1:$Port"
Write-Host 'API: /docs. Detener con Ctrl+C.'
& $ninaPython -m uvicorn nina.main:app --host 127.0.0.1 --port $Port
