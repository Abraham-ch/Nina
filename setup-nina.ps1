param([switch]$DownloadData)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$ninaPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $ninaPython)) {
    py -3.14 -m venv .venv
    if ($LASTEXITCODE) { throw 'No se pudo crear el entorno Python 3.14' }
}
& $ninaPython -m pip install -r requirements.lock.txt
if ($LASTEXITCODE) { throw 'Fallo la instalacion Python' }
Push-Location web
try {
    npm.cmd ci --no-audit --no-fund
    if ($LASTEXITCODE) { throw 'Fallo la instalacion web' }
    npm.cmd run build
    if ($LASTEXITCODE) { throw 'Fallo la compilacion web' }
} finally { Pop-Location }
if ($DownloadData) {
    & $ninaPython scripts/bootstrap_data.py
    if ($LASTEXITCODE) { throw 'Descarga incompleta; vuelve a ejecutar para reanudar' }
    & $ninaPython -m nina.ingest
    if ($LASTEXITCODE) { throw 'Fallo la importacion' }
    & $ninaPython -m nina.science
    if ($LASTEXITCODE) { throw 'Fallo la calibracion exploratoria' }
}
Write-Host 'Preparacion terminada. Ejecuta .\start-nina.ps1'
