$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$shortRoot = 'C:\Users\Lenovo\Desktop\SonicArm\v8_short'
$vivado = 'D:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat'
if (-not (Test-Path -LiteralPath $vivado)) {
    throw "Vivado 2025.2 not found: $vivado"
}
New-Item -ItemType Directory -Force -Path (Join-Path $root 'logs'), (Join-Path $root 'reports') | Out-Null
$shortItem = Get-Item -LiteralPath $shortRoot -Force
if (-not (Test-Path -LiteralPath $shortRoot -PathType Container)) {
    throw "Project directory not found: $shortRoot"
}
$savedTemp = $env:TEMP
$savedTmp = $env:TMP
$toolTemp = Join-Path $shortRoot 'tool_temp'
New-Item -ItemType Directory -Force -Path $toolTemp | Out-Null
$env:TEMP = $toolTemp
$env:TMP = $toolTemp
Push-Location $shortRoot
try {
    & $vivado -mode batch -source (Join-Path $shortRoot 'create_vivado_v8.tcl') `
        -log (Join-Path $shortRoot 'logs\vivado_create.log') `
        -journal (Join-Path $shortRoot 'logs\vivado_create.jou')
    if ($LASTEXITCODE -ne 0) {
        throw "FPGA-8 project creation failed with exit code $LASTEXITCODE"
    }
} finally {
    $env:TEMP = $savedTemp
    $env:TMP = $savedTmp
    Pop-Location
}
