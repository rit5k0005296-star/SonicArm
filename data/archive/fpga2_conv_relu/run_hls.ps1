param([ValidateSet('csim','synth','cosim','package')][string]$Stage='csim')
$ErrorActionPreference='Stop'
$targetFolder=$PSScriptRoot
$toolBin='D:\AMDDesignTools\2025.2\Vitis\bin'
# Never replace an existing mapping. W: is separate from V1's V: mapping.
if (Test-Path 'W:\') {
    $mapped = @(& subst) | Where-Object { $_ -match '^W:\\:' }
    if (-not $mapped -or $mapped -notmatch [regex]::Escape($targetFolder)) {
        throw 'W: is occupied by another path. Choose a free drive and update hls_config.cfg.'
    }
} else {
    & subst W: $targetFolder
    if ($LASTEXITCODE -ne 0) { throw 'Could not map W: to the V2 folder' }
}
if (-not (Test-Path (Join-Path $targetFolder 'layer_params.h'))) { throw 'Run prepare_conv_relu.py first' }
Push-Location $targetFolder
try {
    if ($Stage -eq 'synth') {
        & (Join-Path $toolBin 'v++.bat') -c --mode hls --config W:/hls_config.cfg --work_dir W:/hls_workspace/conv_relu
    } else {
        $stageOption='--'+$Stage
        & (Join-Path $toolBin 'vitis-run.bat') --mode hls $stageOption --config W:/hls_config.cfg --work_dir W:/hls_workspace/conv_relu
    }
    if ($LASTEXITCODE -ne 0) { throw ('HLS stage failed: '+$Stage) }
} finally {
    Pop-Location
}
