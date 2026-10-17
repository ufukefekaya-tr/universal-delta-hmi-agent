param([switch]$Offline, [switch]$ForceRuntime)
$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
try {
    if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'Windows x86_64 required' }
    $lock = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'bootstrap.lock.json') | ConvertFrom-Json
    $runtime = $lock.runtimes.windows_x86_64
    $pythonExe = $null
    if (-not $ForceRuntime) {
        $candidate = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
        # Windows App Execution Aliases may open Microsoft Store on a host with
        # no Python. A headless bootstrap must provision its pinned runtime instead.
        if ($candidate -and $candidate.Source -notmatch '[\\/]Microsoft[\\/]WindowsApps[\\/]') {
            & $candidate.Source -c 'import sys; assert sys.version_info[:2] == (3,14) and sys.maxsize > 2**32' 2>$null
            if ($LASTEXITCODE -eq 0) { $pythonExe = $candidate.Source }
        }
    }
    if (-not $pythonExe) {
        $runtimeRoot = Join-Path $repoRoot '.runtime'
        $pythonExe = Join-Path $runtimeRoot $runtime.executable
        if (-not (Test-Path -LiteralPath $pythonExe)) {
            New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
            $archive = Join-Path $repoRoot ('runtime-bundle/' + $runtime.filename)
            if (-not (Test-Path -LiteralPath $archive)) {
                if ($Offline) { throw 'OFFLINE_RUNTIME_MISSING' }
                if (-not $runtime.url.StartsWith('https://github.com/astral-sh/python-build-standalone/releases/download/20261013/')) { throw 'Runtime URL outside approved source' }
                $archive = Join-Path $runtimeRoot $runtime.filename
                Invoke-WebRequest -Uri $runtime.url -OutFile $archive
            }
            $hashAlgorithm = [System.Security.Cryptography.SHA256]::Create()
            $archiveStream = [System.IO.File]::OpenRead($archive)
            try { $actualHash = [BitConverter]::ToString($hashAlgorithm.ComputeHash($archiveStream)).Replace('-', '').ToLowerInvariant() }
            finally { $archiveStream.Dispose(); $hashAlgorithm.Dispose() }
            if ($actualHash -ne $runtime.sha256) { throw 'Runtime SHA256 mismatch' }
            $entries = & tar -tzf $archive
            if ($LASTEXITCODE -ne 0) { throw 'Runtime archive listing failed' }
            foreach ($entry in $entries) {
                if ($entry -notmatch '^python/' -or $entry -match '(^|/)\.\.(/|$)|\\|:') { throw 'Unsafe runtime archive path' }
            }
            $stage = Join-Path $runtimeRoot ('stage-' + [Guid]::NewGuid().ToString('N'))
            New-Item -ItemType Directory -Path $stage | Out-Null
            & tar -xzf $archive -C $stage
            if ($LASTEXITCODE -ne 0) { throw 'Runtime extraction failed' }
            Move-Item -LiteralPath (Join-Path $stage 'python') -Destination (Join-Path $runtimeRoot 'python')
        }
    }
    & $pythonExe -c 'import sys; assert sys.version_info[:2] == (3,14) and sys.maxsize > 2**32'
    if ($LASTEXITCODE -ne 0) { throw 'Selected Python runtime is incomplete or incompatible' }
    $arguments = @((Join-Path $PSScriptRoot 'build_release.py'), '--install')
    if ($Offline) { $arguments += '--offline' }
    & $pythonExe @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Package installation failed' }
} catch {
    [Console]::Error.WriteLine((@{ status = 'BLOCKED'; code = 'BOOTSTRAP_FAILED'; detail = $_.Exception.Message } | ConvertTo-Json -Compress))
    exit 1
}
