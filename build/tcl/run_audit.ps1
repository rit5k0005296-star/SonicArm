. (Join-Path $PSScriptRoot "..\scripts\resolve_vivado.ps1")
$vivado = Resolve-VivadoExecutable
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $vivado)) {
    throw "Vivado not found: $vivado"
}
& $vivado -mode batch -source (Join-Path $PSScriptRoot 'audit_fpga10.tcl') -log (Join-Path $PSScriptRoot 'logs\vivado_audit.log') -journal (Join-Path $PSScriptRoot 'logs\vivado_audit.jou')
if ($LASTEXITCODE -ne 0) {
    throw "Vivado audit failed with exit code $LASTEXITCODE"
}
