$ErrorActionPreference='Stop'
$taskPython='E:\condaData\envs_dirs\python3.11\python.exe'
Push-Location $PSScriptRoot
try {
    foreach($taskScript in @('tests/audit_implementation.py','verify_local_evidence.py','make_board_package.py','tests/audit_manual_package.py','tests/write_release_report.py')) {
        & $taskPython -B $taskScript
        if($LASTEXITCODE -ne 0){throw "Release gate failed: $taskScript"}
    }
    Write-Output 'V6_VERIFIED_MANUAL_PACKAGE_READY BOARD_UNTESTED'
} finally {Pop-Location}
