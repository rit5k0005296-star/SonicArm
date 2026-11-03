param([ValidateSet('pw','fcm','shared_pw','shared_fcm')][string]$Kernel='pw',
      [ValidateSet('csim','synth','cosim','package')][string]$Stage='csim')
$ErrorActionPreference='Stop'
$toolBin='D:\AMDDesignTools\2025.2\Vitis\bin'
$shortRoot=Join-Path (Split-Path (Split-Path (Split-Path $PSScriptRoot))) 'v7_short'
if (Test-Path -LiteralPath $shortRoot) {
    $item=Get-Item -LiteralPath $shortRoot -Force
    if (-not ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) -or
        [IO.Path]::GetFullPath([string]$item.Target).TrimEnd('\') -ne
        [IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\')) {
        throw 'v7_short exists but is not the isolated FPGA-7 junction.'
    }
} else {
    $null=New-Item -ItemType Junction -Path $shortRoot -Target $PSScriptRoot
}
$taskTemp=$env:TEMP
$taskTmp=$env:TMP
Push-Location $shortRoot
try {
    $null=New-Item -ItemType Directory -Path (Join-Path $shortRoot 'tool_temp') -Force
    $env:TEMP=(Join-Path $shortRoot 'tool_temp');$env:TMP=$env:TEMP
    if ($Stage -eq 'synth') {
        & (Join-Path $toolBin 'v++.bat') -c --mode hls --config "$Kernel.cfg" --work_dir "hls/$Kernel"
    } else {
        & (Join-Path $toolBin 'vitis-run.bat') --mode hls ('--'+$Stage) --config "$Kernel.cfg" --work_dir "hls/$Kernel"
    }
    if ($LASTEXITCODE -ne 0) { throw "V7 $Kernel $Stage failed." }
} finally { $env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location }
