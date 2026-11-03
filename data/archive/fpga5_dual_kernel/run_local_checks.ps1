param([ValidateSet('packing','monitor','fcm','desktop','all')][string]$Stage='all',
      [string]$Python='E:\condaData\envs_dirs\python3.11\python.exe')
$ErrorActionPreference='Stop'
$toolBin='D:\AMDDesignTools\2025.2\Vivado\bin'
if (Test-Path 'W:\') {
    $taskMapping=@(& subst) | Where-Object { $_ -match '^W:\\:' }
    if (-not $taskMapping -or $taskMapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'W: occupied by another directory' }
} else {
    & subst W: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot map V5 short path' }
}
$taskTemp=$env:TEMP;$taskTmp=$env:TMP;$taskPath=$env:PATH
Push-Location 'W:\'
try {
    $env:TEMP='W:/tool_temp';$env:TMP='W:/tool_temp'
    $env:PATH='D:\msys64\ucrt64\bin;'+$env:PATH
    if ($Stage -in @('packing','desktop','all')) {
        & 'D:\msys64\ucrt64\bin\g++.exe' -O2 -std=c++14 -DV5_PORTABLE -Isrc -o tests/test_packed.exe tests/test_packed.cpp
        if ($LASTEXITCODE -ne 0) { throw 'Packed fragment test build failed' }
        & 'W:/tests/test_packed.exe' *> 'W:/logs/packed_bytes.log'
        if ($LASTEXITCODE -ne 0) { throw 'Packed fragment/guard test failed' }
    }
    if ($Stage -in @('monitor','all')) {
        & $Python -B 'W:/tests/make_monitor_wrapper.py'
        if ($LASTEXITCODE -ne 0) { throw 'Monitor wrapper generation failed' }
        Push-Location 'W:\rtl_sim'
        try {
            & (Join-Path $toolBin 'xvlog.bat') -sv -work xil_defaultlib 'W:/rtl/axi_perf_monitor.v' 'W:/rtl/axi_perf_wrapper.v' 'W:/rtl/tb_axi_perf_monitor.sv' 'W:/rtl/tb_axi_perf_wrapper.sv' *> 'W:/logs/monitor_compile.log'
            if ($LASTEXITCODE -ne 0) { throw 'Monitor RTL compile failed' }
            & (Join-Path $toolBin 'xelab.bat') xil_defaultlib.tb_axi_perf_monitor -s v5_monitor *> 'W:/logs/monitor_elab.log'
            if ($LASTEXITCODE -ne 0) { throw 'Monitor elaboration failed' }
            & (Join-Path $toolBin 'xsim.bat') v5_monitor -runall -log 'W:/logs/monitor_sim.log' *> 'W:/logs/monitor_console.log'
            if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath 'W:/logs/monitor_sim.log' -Pattern 'V5_MONITOR_RTL_PASS' -Quiet)) { throw 'Monitor simulation failed' }
            & (Join-Path $toolBin 'xelab.bat') xil_defaultlib.tb_axi_perf_wrapper -s v5_monitor_wrapper *> 'W:/logs/monitor_wrapper_elab.log'
            if ($LASTEXITCODE -ne 0) { throw 'Monitor wrapper elaboration failed' }
            & (Join-Path $toolBin 'xsim.bat') v5_monitor_wrapper -runall -log 'W:/logs/monitor_wrapper_sim.log' *> 'W:/logs/monitor_wrapper_console.log'
            if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath 'W:/logs/monitor_wrapper_sim.log' -Pattern 'V5_MONITOR_WRAPPER_RTL_PASS' -Quiet)) { throw 'Monitor wrapper simulation failed' }
        } finally { Pop-Location }
    }
    if ($Stage -in @('fcm','all')) {
        & $Python -B 'W:/tests/make_rtl_harness.py'
        if ($LASTEXITCODE -ne 0) { throw 'Independent RTL test generation failed' }
        Push-Location 'W:\rtl_kernel_sim'
        try {
            & (Join-Path $toolBin 'xvlog.bat') -prj sources.prj *> 'W:/logs/fcm_independent_compile.log'
            if ($LASTEXITCODE -ne 0) { throw 'FCM RTL compile failed' }
            & (Join-Path $toolBin 'xelab.bat') xil_defaultlib.tb_fcm_axi -s fcm_axi -debug typical *> 'W:/logs/fcm_independent_elab.log'
            if ($LASTEXITCODE -ne 0) { throw 'FCM RTL elaboration failed' }
            & (Join-Path $toolBin 'xsim.bat') fcm_axi -runall -log 'W:/logs/fcm_independent_rtl.log' *> 'W:/logs/fcm_independent_console.log'
            if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath 'W:/logs/fcm_independent_rtl.log' -Pattern 'V5_FCM_INDEPENDENT_RTL_PASS' -Quiet)) { throw 'Independent FCM RTL simulation failed' }
        } finally { Pop-Location }
    }
    if ($Stage -in @('desktop','all')) {
        & 'D:\msys64\ucrt64\bin\g++.exe' -O2 -std=c++14 -DV5_PORTABLE -Isrc -Itests -shared -o tests/v5_native.dll tests/native_exports.cpp src/pointwise.cpp src/fcm.cpp
        if ($LASTEXITCODE -ne 0) { throw 'Native V5 C++ build failed' }
        & $Python -B 'W:/tests/desktop_workflow_check.py' *> 'W:/logs/desktop_workflow.log'
        if ($LASTEXITCODE -ne 0) { throw 'Desktop workflow failed' }
    }
    Write-Output "V5_LOCAL_CHECK_COMPLETE $Stage"
} finally {
    $env:TEMP=$taskTemp;$env:TMP=$taskTmp;$env:PATH=$taskPath
    Pop-Location
}
