. (Join-Path $PSScriptRoot "..\scripts\resolve_vivado.ps1")
$vivado = Resolve-VivadoExecutable
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $vivado)) { throw "Vivado not found: $vivado" }
& $vivado -mode batch -source (Join-Path $PSScriptRoot 'patch_vdma_irq.tcl')
if ($LASTEXITCODE -ne 0) { throw "VDMA IRQ patch failed: $LASTEXITCODE" }
