param([switch]$DownloadData)
$ErrorActionPreference = 'Stop'
$workspace = $PSScriptRoot
$application = Join-Path $workspace 'mvp'
$ninaPython = Join-Path $application '.venv\Scripts\python.exe'
Push-Location -LiteralPath $workspace
try {
    if (-not (Test-Path -LiteralPath $ninaPython)) {
        py -3.14 -m venv (Join-Path $application '.venv')
        if ($LASTEXITCODE) { throw 'No se pudo crear el entorno Python' }
    }
    & $ninaPython -m pip install -r (Join-Path $application 'requirements.lock.txt')
    if ($LASTEXITCODE) { throw 'Fallo la instalacion Python' }
    Push-Location -LiteralPath (Join-Path $application 'web')
    try {
        npm.cmd ci --no-audit --no-fund
        if ($LASTEXITCODE) { throw 'Fallo la instalacion web' }
        npm.cmd run build
        if ($LASTEXITCODE) { throw 'Fallo la compilacion web' }
    } finally { Pop-Location }
    $boundaryFolder = Join-Path $workspace 'data\boundaries'
    New-Item -ItemType Directory -Path $boundaryFolder -Force | Out-Null
    foreach ($filename in @('departments.geojson','provenance.json')) {
        $destination = Join-Path $boundaryFolder $filename
        if (-not (Test-Path -LiteralPath $destination)) {
            Copy-Item -LiteralPath (Join-Path $application "data\boundaries\$filename") -Destination $destination
        }
    }
    if ($DownloadData) {
        Push-Location -LiteralPath $application
        try {
            & $ninaPython scripts/bootstrap_data.py
            if ($LASTEXITCODE) { throw 'Descarga incompleta; vuelve a ejecutar para reanudar' }
            & $ninaPython -m nina.ingest
            if ($LASTEXITCODE) { throw 'Fallo la importacion' }
            & $ninaPython -m nina.science
            if ($LASTEXITCODE) { throw 'Fallo la calibracion exploratoria' }
        } finally { Pop-Location }
    }
} finally { Pop-Location }
Write-Host 'Preparacion terminada. Ejecuta .\start-nina.ps1 desde la raiz.'
