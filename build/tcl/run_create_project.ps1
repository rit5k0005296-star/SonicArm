. (Join-Path $PSScriptRoot "..\scripts\resolve_vivado.ps1")
$vivado = Resolve-VivadoExecutable
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $vivado)) { throw "Vivado not found: $vivado" }
& $vivado -mode batch -nojournal -nolog -source (Join-Path $PSScriptRoot 'create_fpga10.tcl')
if ($LASTEXITCODE -ne 0) { throw "Vivado project creation failed: $LASTEXITCODE" }
