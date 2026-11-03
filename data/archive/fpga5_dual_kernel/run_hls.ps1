param([ValidateSet('pw','fcm')][string]$Kernel='pw',
      [ValidateSet('csim','synth','cosim','package')][string]$Stage='csim')
$ErrorActionPreference='Stop'
$toolBin='D:\AMDDesignTools\2025.2\Vitis\bin'
if (Test-Path 'W:\') {
    $mapping=@(& subst) | Where-Object { $_ -match '^W:\\:' }
    if (-not $mapping -or $mapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'W: occupied; refusing to remap.' }
} else {
    & subst W: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot map isolated V5 short path.' }
}
$taskTemp=$env:TEMP
$taskTmp=$env:TMP
Push-Location 'W:\'
try {
    $null=New-Item -ItemType Directory -Path 'W:\tool_temp' -Force
    $env:TEMP='W:/tool_temp';$env:TMP='W:/tool_temp'
    if ($Stage -eq 'synth') {
        & (Join-Path $toolBin 'v++.bat') -c --mode hls --config "W:/$Kernel.cfg" --work_dir "W:/hls/$Kernel"
    } else {
        & (Join-Path $toolBin 'vitis-run.bat') --mode hls ('--'+$Stage) --config "W:/$Kernel.cfg" --work_dir "W:/hls/$Kernel"
    }
    if ($LASTEXITCODE -ne 0) { throw "V5 $Kernel $Stage failed." }
} finally { $env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location }
