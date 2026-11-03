$ErrorActionPreference = "Stop"
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRoot = Join-Path $RepoRoot "src\ps"
$TestsRoot = Join-Path $RepoRoot "sim\tests"

$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $RuntimeRoot
    Push-Location $RuntimeRoot
    try {
        python -m unittest discover -s $TestsRoot -v
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:PYTHONPATH = $oldPythonPath
}

