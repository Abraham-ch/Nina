param([switch]$DownloadData)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { python -m venv .venv; if ($LASTEXITCODE) { throw 'No se pudo crear el entorno Python' } }
& .\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
if ($LASTEXITCODE) { throw 'Falló la instalación Python' }
Push-Location web
try {
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE) { throw 'Falló la instalación web' }
    npm.cmd run build
    if ($LASTEXITCODE) { throw 'Falló la compilación web' }
} finally { Pop-Location }
if ($DownloadData) {
    & .\.venv\Scripts\python.exe scripts/bootstrap_data.py
    if ($LASTEXITCODE) { throw 'Descarga incompleta; vuelve a ejecutar para reanudar' }
    & .\.venv\Scripts\python.exe -m nina.ingest
    if ($LASTEXITCODE) { throw 'Falló la importación' }
    & .\.venv\Scripts\python.exe -m nina.science
    if ($LASTEXITCODE) { throw 'Falló la calibración exploratoria' }
}
Write-Host 'Preparación terminada. Ejecuta .\start-nina.ps1'
