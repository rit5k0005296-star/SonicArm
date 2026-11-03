param([ValidateSet('csim','synth','cosim','package')][string]$Stage='csim')
$ErrorActionPreference='Stop'
$toolBin='D:\AMDDesignTools\2025.2\Vitis\bin'
if (Test-Path 'V:\') {
    $mapping=@(& subst) | Where-Object { $_ -match '^V:\\:' }
    if (-not $mapping -or $mapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'V: is occupied; refusing to change it.' }
} else {
    & subst V: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not create V: short path.' }
}
Push-Location 'V:\'
try {
    if ($Stage -eq 'synth') {
        & (Join-Path $toolBin 'v++.bat') -c --mode hls --config V:/hls_config.cfg --work_dir V:/hls_workspace/fcm
    } else {
        & (Join-Path $toolBin 'vitis-run.bat') --mode hls ('--'+$Stage) --config V:/hls_config.cfg --work_dir V:/hls_workspace/fcm
    }
    if ($LASTEXITCODE -ne 0) { throw ('HLS stage failed: '+$Stage) }
} finally { Pop-Location }
