param([ValidateSet('packing','monitor','fcm','desktop','all')][string]$Stage='all',
      [string]$Python='E:\condaData\envs_dirs\python3.11\python.exe')
$ErrorActionPreference='Stop'
$toolBin='D:\AMDDesignTools\2025.2\Vivado\bin'
if (Test-Path 'V:\') {
    $taskMapping=@(& subst) | Where-Object { $_ -match '^V:\\:' }
    if (-not $taskMapping -or $taskMapping -notmatch [regex]::Escape($PSScriptRoot)) { throw 'V: occupied by another directory' }
} else {
    & subst V: $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Cannot map V6 short path' }
}
$taskTemp=$env:TEMP;$taskTmp=$env:TMP;$taskPath=$env:PATH
Push-Location 'V:\'
try {
    $env:TEMP='V:/tool_temp';$env:TMP='V:/tool_temp'
    $env:PATH='D:\msys64\ucrt64\bin;'+$env:PATH
    if ($Stage -in @('packing','desktop','all')) {
        & 'D:\msys64\ucrt64\bin\g++.exe' -O2 -std=c++14 -DV6_PORTABLE -Isrc -o tests/test_packed.exe tests/test_packed.cpp
        if ($LASTEXITCODE -ne 0) { throw 'Packed fragment test build failed' }
        & 'V:/tests/test_packed.exe' *> 'V:/logs/packed_bytes.log'
        if ($LASTEXITCODE -ne 0) { throw 'Packed fragment/guard test failed' }
    }
    if ($Stage -in @('monitor','all')) {
        & $Python -B 'V:/tests/make_monitor_wrapper.py'
        if ($LASTEXITCODE -ne 0) { throw 'Monitor wrapper generation failed' }
        Push-Location 'V:\rtl_sim'
        try {
            & (Join-Path $toolBin 'xvlog.bat') -sv -work xil_defaultlib 'V:/rtl/axi_perf_monitor.v' 'V:/rtl/axi_perf_wrapper.v' 'V:/rtl/tb_axi_perf_monitor.sv' 'V:/rtl/tb_axi_perf_wrapper.sv' *> 'V:/logs/monitor_compile.log'
            if ($LASTEXITCODE -ne 0) { throw 'Monitor RTL compile failed' }
            & (Join-Path $toolBin 'xelab.bat') xil_defaultlib.tb_axi_perf_monitor -s v6_monitor *> 'V:/logs/monitor_elab.log'
            if ($LASTEXITCODE -ne 0) { throw 'Monitor elaboration failed' }
            & (Join-Path $toolBin 'xsim.bat') v6_monitor -runall -log 'V:/logs/monitor_sim.log' *> 'V:/logs/monitor_console.log'
            if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath 'V:/logs/monitor_sim.log' -Pattern 'V6_MONITOR_RTL_PASS' -Quiet)) { throw 'Monitor simulation failed' }
            & (Join-Path $toolBin 'xelab.bat') xil_defaultlib.tb_axi_perf_wrapper -s v6_monitor_wrapper *> 'V:/logs/monitor_wrapper_elab.log'
            if ($LASTEXITCODE -ne 0) { throw 'Monitor wrapper elaboration failed' }
            & (Join-Path $toolBin 'xsim.bat') v6_monitor_wrapper -runall -log 'V:/logs/monitor_wrapper_sim.log' *> 'V:/logs/monitor_wrapper_console.log'
            if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath 'V:/logs/monitor_wrapper_sim.log' -Pattern 'V6_MONITOR_WRAPPER_RTL_PASS' -Quiet)) { throw 'Monitor wrapper simulation failed' }
        } finally { Pop-Location }
    }
    if ($Stage -in @('fcm','all')) {
        & $Python -B 'V:/tests/make_rtl_harness.py'
        if ($LASTEXITCODE -ne 0) { throw 'Independent RTL test generation failed' }
        Push-Location 'V:\rtl_kernel_sim'
        try {
            & (Join-Path $toolBin 'xvlog.bat') -prj sources.prj *> 'V:/logs/fcm_independent_compile.log'
            if ($LASTEXITCODE -ne 0) { throw 'FCM RTL compile failed' }
            & (Join-Path $toolBin 'xelab.bat') xil_defaultlib.tb_fcm_axi -s fcm_axi -debug typical *> 'V:/logs/fcm_independent_elab.log'
            if ($LASTEXITCODE -ne 0) { throw 'FCM RTL elaboration failed' }
            & (Join-Path $toolBin 'xsim.bat') fcm_axi -runall -log 'V:/logs/fcm_independent_rtl.log' *> 'V:/logs/fcm_independent_console.log'
            if ($LASTEXITCODE -ne 0 -or -not (Select-String -LiteralPath 'V:/logs/fcm_independent_rtl.log' -Pattern 'V6_FCM_INDEPENDENT_RTL_PASS' -Quiet)) { throw 'Independent FCM RTL simulation failed' }
        } finally { Pop-Location }
    }
    if ($Stage -in @('desktop','all')) {
        & 'D:\msys64\ucrt64\bin\g++.exe' -O2 -std=c++14 -DV6_PORTABLE -Isrc -Itests -shared -o tests/v6_native.dll tests/native_exports.cpp src/pointwise.cpp src/fcm.cpp
        if ($LASTEXITCODE -ne 0) { throw 'Native V6 C++ build failed' }
        & $Python -B 'V:/tests/desktop_workflow_check.py' *> 'V:/logs/desktop_workflow.log'
        if ($LASTEXITCODE -ne 0) { throw 'Desktop workflow failed' }
    }
    Write-Output "V6_LOCAL_CHECK_COMPLETE $Stage"
} finally {
    $env:TEMP=$taskTemp;$env:TMP=$taskTmp;$env:PATH=$taskPath
    Pop-Location
}
