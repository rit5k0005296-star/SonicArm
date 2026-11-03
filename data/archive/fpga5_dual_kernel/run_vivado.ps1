param([ValidateSet('probe','create','build','collect','repair_monitor','timing_help','close_timing','restart_placement','restart_full_implementation','inspect_implementation','gui')][string]$Stage='create')
$ErrorActionPreference='Stop'
if (Test-Path 'W:\') {
    $mapping=@(& subst) | Where-Object { $_ -match '^W:\\:' }
    if (-not $mapping -or $mapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'W: occupied; refusing to remap.' }
} else {
    & subst W: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot map isolated V5 short path.' }
}
$taskTemp=$env:TEMP;$taskTmp=$env:TMP
Push-Location 'W:\'
try {
    $null=New-Item -ItemType Directory -Path 'W:\tool_temp' -Force
    $env:TEMP='W:/tool_temp';$env:TMP='W:/tool_temp'
    $mode=if($Stage -eq 'gui'){'gui'}else{'batch'}
    $script=if($Stage -eq 'probe'){'W:/probe_pins.tcl'}elseif($Stage -eq 'gui'){'W:/open_project.tcl'}elseif($Stage -eq 'repair_monitor'){'W:/repair_monitor.tcl'}elseif($Stage -eq 'timing_help'){'W:/timing_help.tcl'}elseif($Stage -eq 'close_timing'){'W:/close_timing.tcl'}elseif($Stage -eq 'restart_placement'){'W:/restart_placement.tcl'}elseif($Stage -eq 'restart_full_implementation'){'W:/restart_full_implementation.tcl'}elseif($Stage -eq 'inspect_implementation'){'W:/inspect_implementation.tcl'}else{"W:/${Stage}_vivado.tcl"}
    & 'D:\AMDDesignTools\2025.2\Vivado\bin\vivado.bat' -mode $mode -source $script -log "W:/logs/vivado_$Stage.log" -journal "W:/logs/vivado_$Stage.jou"
    if ($LASTEXITCODE -ne 0) { throw "V5 Vivado $Stage failed." }
} finally { $env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location }
