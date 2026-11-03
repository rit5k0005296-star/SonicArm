param(
    [string]$OutputRoot = ""
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $RepoRoot "board\generated\fpga_10_$Stamp"
}

if (Test-Path -LiteralPath $OutputRoot) {
    throw "Output already exists; choose a new directory: $OutputRoot"
}

New-Item -ItemType Directory -Path $OutputRoot | Out-Null
New-Item -ItemType Directory -Path (Join-Path $OutputRoot "arm_control") | Out-Null
New-Item -ItemType Directory -Path (Join-Path $OutputRoot "fpga_v8") | Out-Null

$runtimeRoot = Join-Path $RepoRoot "src\ps"
$rootFiles = @(
    "app.py", "controller.py", "board_runtime.py", "v9_audio.py", "v9_core.py",
    "native_display.py", "arm_integration.py", "config.json", "diagnose_audio_run.py",
    "run_validation.py", "verify_package.py", "build_notebook.py",
    "NotoSansSC-Regular.otf", "NotoSansSC-Bold.otf"
)
foreach ($file in $rootFiles) {
    Copy-Item -LiteralPath (Join-Path $runtimeRoot $file) -Destination $OutputRoot
}

Copy-Item -Path (Join-Path $runtimeRoot "arm\*") -Destination (Join-Path $OutputRoot "arm_control") -Recurse
Copy-Item -LiteralPath (Join-Path $runtimeRoot "ui") -Destination $OutputRoot -Recurse
Copy-Item -LiteralPath (Join-Path $RepoRoot "src\models\kws\tc_resnet3\runtime") -Destination (Join-Path $OutputRoot "tc_resnet3_ps") -Recurse
Copy-Item -LiteralPath (Join-Path $RepoRoot "src\models\kws\tc_resnet2\runtime") -Destination (Join-Path $OutputRoot "tc_resnet2_ps") -Recurse
Copy-Item -LiteralPath (Join-Path $RepoRoot "src\models\voiceprint\v8_runtime.py") -Destination (Join-Path $OutputRoot "fpga_v8\v8_runtime.py")
Copy-Item -Path (Join-Path $RepoRoot "src\models\voiceprint\runtime_bundle\*") -Destination $OutputRoot -Recurse -Force

$artifactRoot = Join-Path $RepoRoot "board\artifacts"
foreach ($file in @("fpga10_audio_hdmi.bit", "fpga10_audio_hdmi.hwh")) {
    $source = Join-Path $artifactRoot $file
    if (-not (Test-Path -LiteralPath $source)) {
        throw "Missing release artifact: $source"
    }
    Copy-Item -LiteralPath $source -Destination $OutputRoot
}

$diagRoot = Join-Path $RepoRoot "board\diagnostics"
Copy-Item -Path (Join-Path $diagRoot "*.py") -Destination $OutputRoot

$hashes = Get-ChildItem -LiteralPath $OutputRoot -File -Recurse | ForEach-Object {
    [pscustomobject]@{
        path = $_.FullName.Substring($OutputRoot.Length + 1).Replace("\", "/")
        sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        bytes = $_.Length
    }
}
$hashes | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $OutputRoot "SHA256_MANIFEST.json") -Encoding utf8

Write-Host "Board package created: $OutputRoot" -ForegroundColor Green

