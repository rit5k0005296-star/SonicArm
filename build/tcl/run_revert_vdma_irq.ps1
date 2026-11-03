. (Join-Path $PSScriptRoot "..\scripts\resolve_vivado.ps1")
$vivado = Resolve-VivadoExecutable
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $vivado)) { throw "Vivado not found: $vivado" }
& $vivado -mode batch -source (Join-Path $PSScriptRoot 'revert_vdma_irq.tcl') 2>&1 |
    Tee-Object -FilePath (Join-Path $PSScriptRoot 'reports\revert_vdma_irq_console.log')
if ($LASTEXITCODE -ne 0) { throw "Vivado IRQ revert failed: $LASTEXITCODE" }
