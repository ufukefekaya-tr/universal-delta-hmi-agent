param([string]$BackendArchive)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
try {
    $lock = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'templates/releases.lock.json') | ConvertFrom-Json
    if (-not $BackendArchive) { $BackendArchive = Join-Path $repoRoot ('bundles/' + $lock.dop_b.archive) }
    if (-not (Test-Path -LiteralPath $BackendArchive -PathType Leaf)) { throw 'PINNED_DOP_B_ARCHIVE_MISSING' }
    if ((Get-FileHash -LiteralPath $BackendArchive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.dop_b.sha256) { throw 'ARCHIVE_HASH_MISMATCH' }
    $target = Join-Path $repoRoot '.local/backends/dop_b'
    if (Test-Path -LiteralPath $target) { throw 'EXISTING_BACKEND_PRESERVED: use a fresh checkout for reinstall' }
    $check = [System.IO.DirectoryInfo]$repoRoot
    while ($check) {
        if ($check.Exists -and ($check.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw 'LINKED_INSTALL_ROOT' }
        $check = $check.Parent
    }
    foreach ($part in @('.local', '.local/backends')) {
        $path = Join-Path $repoRoot $part
        if ((Test-Path -LiteralPath $path) -and ((Get-Item -LiteralPath $path).Attributes -band [System.IO.FileAttributes]::ReparsePoint)) { throw 'LINKED_INSTALL_DIRECTORY' }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
    $stage = Join-Path (Split-Path $target -Parent) ('stage-' + [Guid]::NewGuid().ToString('N'))
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead((Resolve-Path -LiteralPath $BackendArchive).Path)
    try {
        foreach ($entry in $archive.Entries) {
            if ($entry.FullName -match '(^/|\\|:|(^|/)\.\.(/|$))') { throw 'UNSAFE_ARCHIVE_ENTRY' }
        }
    } finally { $archive.Dispose() }
    [System.IO.Compression.ZipFile]::ExtractToDirectory((Resolve-Path -LiteralPath $BackendArchive).Path, $stage)
    Move-Item -LiteralPath $stage -Destination $target
    & (Join-Path $target 'scripts/bootstrap.ps1') -Offline -ForceRuntime
    if ($LASTEXITCODE -ne 0) { throw 'BACKEND_BOOTSTRAP_FAILED' }
    & (Join-Path $target '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'finish_install.py')
    if ($LASTEXITCODE -ne 0) { throw 'GATEWAY_INSTALL_FAILED' }
} catch {
    [Console]::Error.WriteLine((@{status='BLOCKED'; detail=$_.Exception.Message} | ConvertTo-Json -Compress))
    exit 1
}
