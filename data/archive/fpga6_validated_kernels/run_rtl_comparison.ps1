$ErrorActionPreference='Stop'
$taskTemp=$env:TEMP;$taskTmp=$env:TMP
$taskPython='E:\condaData\envs_dirs\python3.11\python.exe'
$taskBin='D:\AMDDesignTools\2025.2\Vivado\bin'
Push-Location $PSScriptRoot
try {
    & '.\run_local_checks.ps1' -Stage fcm *> 'logs/rtl_v6_flow.log'
    if($LASTEXITCODE -ne 0){throw 'V6 independent RTL failed'}
    Write-Output 'V6_INDEPENDENT_AXI_RTL_COMPLETE'
    & $taskPython -B tests/make_rtl_harness.py --v5
    if($LASTEXITCODE -ne 0){throw 'V5 reference harness failed'}
    $env:TEMP='V:/tool_temp';$env:TMP='V:/tool_temp'
    Push-Location 'V:/rtl_v5_reference'
    try {
        & (Join-Path $taskBin 'xvlog.bat') -prj sources.prj *> 'V:/logs/v5_reference_compile.log'
        if($LASTEXITCODE -ne 0){throw 'V5 reference compile failed'}
        & (Join-Path $taskBin 'xelab.bat') xil_defaultlib.tb_fcm_axi -s fcm_v5_reference -debug typical *> 'V:/logs/v5_reference_elab.log'
        if($LASTEXITCODE -ne 0){throw 'V5 reference elaboration failed'}
        & (Join-Path $taskBin 'xsim.bat') fcm_v5_reference -runall -log 'V:/logs/v5_reference_rtl.log' *> 'V:/logs/v5_reference_console.log'
        if($LASTEXITCODE -ne 0 -or -not(Select-String -LiteralPath 'V:/logs/v5_reference_rtl.log' -Pattern 'V5_REFERENCE_FCM_RTL_PASS' -Quiet)){throw 'V5 reference RTL failed'}
    } finally {Pop-Location}
    Write-Output 'V5_V6_SAME_HARNESS_AXI_COMPARISON_COMPLETE'
} finally {$env:TEMP=$taskTemp;$env:TMP=$taskTmp;Pop-Location}
