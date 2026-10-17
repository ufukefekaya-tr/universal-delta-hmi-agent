param([switch]$Offline, [switch]$ForceRuntime)
& (Join-Path $PSScriptRoot 'bootstrap.ps1') -Offline:$Offline -ForceRuntime:$ForceRuntime
exit $LASTEXITCODE
