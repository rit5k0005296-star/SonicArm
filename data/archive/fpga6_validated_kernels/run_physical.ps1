$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    foreach($taskKernel in @('pw','fcm')) {
        if(-not(Select-String -LiteralPath "logs/hls_${taskKernel}_cosim.log" -Pattern 'C/RTL co-simulation finished: PASS' -Quiet)){throw "Missing $taskKernel C/RTL PASS"}
        if(-not(Test-Path -LiteralPath "hls/$taskKernel/hls/impl/ip/component.xml")){throw 'Missing current IP'}
    }
    & '.\run_vivado.ps1' -Stage create *> 'logs/physical_create_console.log'
    if($LASTEXITCODE -ne 0){throw 'Vivado create failed'}
    Write-Output 'V6_FRESH_MATCHED_IP_BD_CREATED'
    & '.\run_vivado.ps1' -Stage build *> 'logs/physical_build_console.log'
    if($LASTEXITCODE -ne 0){throw 'Vivado build failed'}
    Write-Output 'V6_PHYSICAL_IMPLEMENTATION_COMPLETE'
} finally {Pop-Location}
