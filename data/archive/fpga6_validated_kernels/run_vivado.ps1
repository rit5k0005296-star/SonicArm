param([ValidateSet('create','build','collect','gui')][string]$Stage='create')
$ErrorActionPreference='Stop'
if (Test-Path 'V:\') {
    $mapping=@(& subst) | Where-Object { $_ -match '^V:\\:' }
    if (-not $mapping -or $mapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'V: occupied; refusing to remap.' }
} else {
    & subst V: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot map isolated V6 short path.' }
}
$taskTemp=$env:TEMP;$taskTmp=$env:TMP
Push-Location 'V:\'
try {
    $null=New-Item -ItemType Directory -Path 'V:\tool_temp' -Force
    $env:TEMP='V:/tool_temp';$env:TMP='V:/tool_temp'
    $mode=if($Stage -eq 'gui'){'gui'}else{'batch'}
    $script=if($Stage -eq 'gui'){'V:/open_project.tcl'}else{"V:/${Stage}_vivado.tcl"}
    & 'D:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode $mode -source $script -log "V:/logs/vivado_$Stage.log" -journal "V:/logs/vivado_$Stage.jou"
    if ($LASTEXITCODE -ne 0) { throw "V6 Vivado $Stage failed." }
} finally { $env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location }
