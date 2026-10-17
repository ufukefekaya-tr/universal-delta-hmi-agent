param([string]$BackendArchive, [switch]$Offline)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
function Assert-NoLink([string]$Candidate) {
    $cursor = [System.IO.Path]::GetFullPath($Candidate)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            if ((Get-Item -Force -LiteralPath $cursor).Attributes -band [System.IO.FileAttributes]::ReparsePoint) { throw 'LINKED_INSTALL_PATH' }
        }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
$oldPythonPath = $env:PYTHONPATH
$oldPythonHome = $env:PYTHONHOME
try {
    Assert-NoLink $repoRoot
    foreach ($part in @('.local','.local/downloads','.local/backends','.venv')) { Assert-NoLink (Join-Path $repoRoot $part) }
    if (Test-Path -LiteralPath (Join-Path $repoRoot '.venv')) { throw 'EXISTING_GATEWAY_ENVIRONMENT_PRESERVED' }
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    $lock = Get-Content -Raw -LiteralPath (Join-Path $repoRoot 'templates/releases.lock.json') | ConvertFrom-Json
    if (-not $BackendArchive) {
        $BackendArchive = Join-Path $repoRoot ('bundles/' + $lock.dop_b.archive)
        if (-not (Test-Path -LiteralPath $BackendArchive)) {
            if ($Offline) { throw 'OFFLINE_BACKEND_ARCHIVE_MISSING' }
            $cache = Join-Path $repoRoot '.local/downloads'
            New-Item -ItemType Directory -Force -Path $cache | Out-Null
            $BackendArchive = Join-Path $cache $lock.dop_b.archive
            Assert-NoLink $BackendArchive
            if (-not (Test-Path -LiteralPath $BackendArchive)) {
                if ($lock.dop_b.url -notlike 'https://github.com/ufukefekaya-tr/universal-delta-hmi-agent/releases/download/*') { throw 'UNTRUSTED_RELEASE_URL' }
                $download = Join-Path $cache ('download-' + [Guid]::NewGuid().ToString('N') + '.tmp')
                Assert-NoLink $download
                $stream = [System.IO.File]::Open($download, [System.IO.FileMode]::CreateNew)
                $stream.Dispose()
                Invoke-WebRequest -Uri $lock.dop_b.url -OutFile $download
                if ((Get-FileHash -LiteralPath $download -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.dop_b.sha256) { throw 'DOWNLOAD_HASH_MISMATCH' }
                Assert-NoLink $BackendArchive
                Move-Item -LiteralPath $download -Destination $BackendArchive
            }
        }
    }
    Assert-NoLink $BackendArchive
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
    $boundary = [System.IO.Path]::GetFullPath((Join-Path $repoRoot '.local/backends')) + [System.IO.Path]::DirectorySeparatorChar
    if (-not ([System.IO.Path]::GetFullPath($stage).StartsWith($boundary)) -or -not ([System.IO.Path]::GetFullPath($target).StartsWith($boundary))) { throw 'INSTALL_PATH_ESCAPE' }
    Move-Item -LiteralPath $stage -Destination $target
    & (Join-Path $target 'scripts/bootstrap.ps1') -Offline -ForceRuntime
    if ($LASTEXITCODE -ne 0) { throw 'BACKEND_BOOTSTRAP_FAILED' }
    & (Join-Path $target '.venv/Scripts/python.exe') -I -B (Join-Path $PSScriptRoot 'finish_install.py')
    if ($LASTEXITCODE -ne 0) { throw 'GATEWAY_INSTALL_FAILED' }
} catch {
    [Console]::Error.WriteLine((@{status='BLOCKED'; detail=$_.Exception.Message} | ConvertTo-Json -Compress))
    exit 1
} finally {
    $env:PYTHONPATH = $oldPythonPath
    $env:PYTHONHOME = $oldPythonHome
}
