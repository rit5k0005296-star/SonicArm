param([string]$Python='E:\condaData\envs_dirs\python3.11\python.exe')
$ErrorActionPreference='Stop'
$taskPath=$env:PATH
Push-Location $PSScriptRoot
try {
    $env:PATH='D:\msys64\ucrt64\bin;'+$env:PATH
    foreach($taskKernel in @('pointwise','fcm')) {
        & 'D:\msys64\ucrt64\bin\g++.exe' -O2 -std=c++14 -DV7_PORTABLE -Isrc -Itests "tests/tb_$taskKernel.cpp" "src/$taskKernel.cpp" -o "tests/tb_$taskKernel.exe"
        if($LASTEXITCODE -ne 0){throw "Native compile failed $taskKernel"}
        $taskCases=if($taskKernel -eq 'pointwise'){'pw'}else{'fcm'}
        & ".\tests\tb_$taskKernel.exe" "tests/${taskCases}_cases" --all *> "logs/native_$taskKernel.log"
        if($LASTEXITCODE -ne 0){throw "Native reference failed $taskKernel"}
    }
    & 'D:\msys64\ucrt64\bin\g++.exe' -O2 -std=c++14 -DV7_PORTABLE -Isrc -o tests/test_packed.exe tests/test_packed.cpp
    if($LASTEXITCODE -ne 0){throw 'Packed compile failed'}
    & '.\tests\test_packed.exe' *> 'logs/packed_bytes.log'
    if($LASTEXITCODE -ne 0){throw 'Packed test failed'}
    Write-Output 'V7_NATIVE_REFERENCE_PASS'
} finally {$env:PATH=$taskPath;Pop-Location}
