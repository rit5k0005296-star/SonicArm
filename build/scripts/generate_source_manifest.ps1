param(
    [string]$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $RepositoryRoot).Path.TrimEnd('\')
$output = Join-Path $root 'SOURCE_MANIFEST.json'

$files = Get-ChildItem -LiteralPath $root -Recurse -File -Force |
    Where-Object {
        $_.FullName -ne $output -and
        $_.FullName -notlike "$root\.git\*"
    } |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($root.Length + 1).Replace('\', '/')
        [ordered]@{
            path = $relative
            bytes = $_.Length
            sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash.ToLowerInvariant()
        }
    }

$manifest = [ordered]@{
    schema_version = 1
    generated_at = [DateTimeOffset]::Now.ToString('yyyy-MM-ddTHH:mm:sszzz')
    file_count = @($files).Count
    files = @($files)
}

$json = $manifest | ConvertTo-Json -Depth 5
[IO.File]::WriteAllText($output, $json + [Environment]::NewLine, [Text.UTF8Encoding]::new($false))
Write-Output "Source manifest created: $output ($(@($files).Count) files)"
