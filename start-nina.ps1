param([int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$workspace = $PSScriptRoot
$application = Join-Path $workspace 'mvp'
$ninaPython = Join-Path $application '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ninaPython)) { throw 'Primero ejecuta .\setup-nina.ps1 desde la raiz del repositorio.' }
if (-not (Test-Path -LiteralPath (Join-Path $application 'web\dist\index.html'))) { throw 'Falta compilar la interfaz: npm.cmd --prefix mvp/web run build' }
Write-Host "NINA: http://127.0.0.1:$Port"
Write-Host 'API: /docs. Detener con Ctrl+C.'
Push-Location -LiteralPath $application
try {
    & $ninaPython -m uvicorn nina.main:app --host 127.0.0.1 --port $Port
} finally { Pop-Location }
