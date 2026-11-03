param([ValidateSet('pw','fcm')][string]$Kernel='pw',
      [ValidateSet('csim','synth','cosim','package')][string]$Stage='csim')
$ErrorActionPreference='Stop'
$toolBin='D:\AMDDesignTools\2025.2\Vitis\bin'
if (Test-Path 'V:\') {
    $mapping=@(& subst) | Where-Object { $_ -match '^V:\\:' }
    if (-not $mapping -or $mapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'V: occupied; refusing to remap.' }
} else {
    & subst V: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot map isolated V6 short path.' }
}
$taskTemp=$env:TEMP
$taskTmp=$env:TMP
Push-Location 'V:\'
try {
    $null=New-Item -ItemType Directory -Path 'V:\tool_temp' -Force
    $env:TEMP='V:/tool_temp';$env:TMP='V:/tool_temp'
    if ($Stage -eq 'synth') {
        & (Join-Path $toolBin 'v++.bat') -c --mode hls --config "V:/$Kernel.cfg" --work_dir "V:/hls/$Kernel"
    } else {
        & (Join-Path $toolBin 'vitis-run.bat') --mode hls ('--'+$Stage) --config "V:/$Kernel.cfg" --work_dir "V:/hls/$Kernel"
    }
    if ($LASTEXITCODE -ne 0) { throw "V6 $Kernel $Stage failed." }
} finally { $env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location }
