param(
    [string]$BoardRoot = "\\192.168.2.99\xilinx\jupyter_notebooks\SonicArm\test_1\fpga_10"
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$ExpectedSuffix = "\jupyter_notebooks\SonicArm\test_1\fpga_10"

if (-not $BoardRoot.EndsWith($ExpectedSuffix, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Board target path validation failed: $BoardRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $BoardRoot "app.py"))) {
    throw "app.py was not found in board target: $BoardRoot"
}
if (-not (Test-Path -LiteralPath (Join-Path $BoardRoot "arm_control\verified_arm_control.py"))) {
    throw "verified_arm_control.py was not found in board target: $BoardRoot"
}

$SourceMap = [ordered]@{
    "app.py" = Join-Path $RepoRoot "src\ps\app.py"
    "controller.py" = Join-Path $RepoRoot "src\ps\controller.py"
    "config.json" = Join-Path $RepoRoot "src\ps\config.json"
    "arm_control\verified_arm_control.py" = Join-Path $RepoRoot "src\ps\arm\verified_arm_control.py"
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $BoardRoot "_backup_before_github_patch_$Stamp"
New-Item -ItemType Directory -Path (Join-Path $BackupRoot "arm_control") -Force | Out-Null

foreach ($relative in $SourceMap.Keys) {
    $boardFile = Join-Path $BoardRoot $relative
    $backupFile = Join-Path $BackupRoot $relative
    $sourceFile = $SourceMap[$relative]
    if (-not (Test-Path -LiteralPath $sourceFile)) {
        throw "Repository source file is missing: $sourceFile"
    }
    Copy-Item -LiteralPath $boardFile -Destination $backupFile -Force
    Copy-Item -LiteralPath $sourceFile -Destination $boardFile -Force
}

$rows = foreach ($relative in $SourceMap.Keys) {
    $sourceFile = $SourceMap[$relative]
    $boardFile = Join-Path $BoardRoot $relative
    $expected = (Get-FileHash -LiteralPath $sourceFile -Algorithm SHA256).Hash
    $actual = (Get-FileHash -LiteralPath $boardFile -Algorithm SHA256).Hash
    [pscustomobject]@{
        File = $relative
        Match = ($expected -eq $actual)
        SHA256 = $actual
    }
}

$rows | Format-Table -AutoSize
if ($rows.Match -contains $false) {
    throw "Post-deployment SHA256 verification failed"
}

Write-Host "Deployment completed. Backup directory: $BackupRoot" -ForegroundColor Green
Write-Host "Return to the PYNQ terminal and start app.py." -ForegroundColor Yellow

