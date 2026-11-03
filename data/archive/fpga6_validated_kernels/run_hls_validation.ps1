$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
    foreach($taskStage in @('csim','synth','cosim','package')) {
        & '.\run_hls.ps1' -Kernel fcm -Stage $taskStage *> "logs/hls_fcm_$taskStage.log"
        if($LASTEXITCODE -ne 0){throw "FCM $taskStage failed"}
        Write-Output "V6_FCM_STAGE_COMPLETE $taskStage"
    }
    & '.\run_hls.ps1' -Kernel pw -Stage package *> 'logs/hls_pw_package.log'
    if($LASTEXITCODE -ne 0){throw 'PW package failed'}
    Write-Output 'V6_HLS_VALIDATION_COMPLETE'
} finally {Pop-Location}
