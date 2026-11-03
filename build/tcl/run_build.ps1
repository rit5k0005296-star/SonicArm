. (Join-Path $PSScriptRoot "..\scripts\resolve_vivado.ps1")
$vivado = Resolve-VivadoExecutable
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $vivado)) { throw "Vivado not found: $vivado" }
$reportDir = Join-Path $PSScriptRoot '..\reports'
New-Item -ItemType Directory -Force -Path $reportDir | Out-Null
& $vivado -mode batch -source (Join-Path $PSScriptRoot 'build_fpga10.tcl') 2>&1 |
    Tee-Object -FilePath (Join-Path $reportDir 'build_console.log')
if ($LASTEXITCODE -ne 0) { throw "Vivado build failed: $LASTEXITCODE" }
