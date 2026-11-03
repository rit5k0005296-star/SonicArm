param([ValidateSet('create','build','collect')][string]$Stage='create')
$ErrorActionPreference='Stop'
$shortRoot=Join-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot))) 'v7_short'
if(-not(Test-Path -LiteralPath $shortRoot)){throw 'Missing isolated v7_short junction.'}
$item=Get-Item -LiteralPath $shortRoot -Force
if(-not($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
   [IO.Path]::GetFullPath([string]$item.Target).TrimEnd('\') -ne [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')){
    throw 'v7_short does not target FPGA-7.'
}
$taskTemp=$env:TEMP;$taskTmp=$env:TMP
Push-Location $shortRoot
try {
    $null=New-Item -ItemType Directory -Path (Join-Path $shortRoot 'tool_temp') -Force
    $env:TEMP=(Join-Path $shortRoot 'tool_temp');$env:TMP=$env:TEMP
    & 'D:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode batch -source "$Stage`_vivado.tcl" `
        -log "logs/vivado_$Stage.log" -journal "logs/vivado_$Stage.jou"
    if($LASTEXITCODE -ne 0){throw "V7 Vivado $Stage failed."}
} finally {$env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location}
