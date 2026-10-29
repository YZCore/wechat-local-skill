[CmdletBinding()]
param(
    [string]$Root,
    [string]$Python,
    [string]$Vault,
    [string]$Group,
    [switch]$Apply,
    [switch]$PrepareModel,
    [switch]$ConnectionOnly
)
$ErrorActionPreference = 'Stop'
if (-not $Root) {
    $Root = if (Test-Path -LiteralPath 'D:\') { 'D:\WeChatBridge' } else { Join-Path $env:USERPROFILE 'Projects\WeChatBridge' }
}
$Root = [IO.Path]::GetFullPath($Root)
$helper = Join-Path $PSScriptRoot 'setup_backend.py'
$pythonArgs = @()
if (-not $Python) {
    $existing = Join-Path $Root 'auto-read\.venv\Scripts\python.exe'
    $local = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
    foreach ($candidate in @($existing, $local)) {
        if (Test-Path -LiteralPath $candidate) { $Python = $candidate; break }
    }
}
if (-not $Python) {
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $found = & $launcher.Source -3.11 -c 'import sys;print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path -LiteralPath $found)) { $Python = $found }
    }
}
if (-not $Python) {
    foreach ($name in @('python', 'python3')) {
        $candidate = Get-Command $name -ErrorAction SilentlyContinue
        if ($candidate -and $candidate.Source -notlike '*\Microsoft\WindowsApps\*') { $Python = $candidate.Source; break }
    }
}
$arguments = @($helper, '--root', $Root)
if ($Apply) { $arguments += '--apply' }
if ($PrepareModel) { $arguments += '--prepare-model' }
if ($ConnectionOnly) { $arguments += '--connection-only' }
if ($Vault) { $arguments += @('--vault', $Vault) }
if ($Group) { $arguments += @('--group', $Group) }
if ($Python) {
    & $Python -X utf8 @arguments
    exit $LASTEXITCODE
}
$uv = Get-Command uv -ErrorAction SilentlyContinue
if ($uv -and ($Apply -or $PrepareModel)) {
    & $uv.Source run --python 3.11 --no-project @arguments
    exit $LASTEXITCODE
}
if (-not $Apply) {
    [pscustomobject]@{ root=$Root; pythonReady=$false; uvAvailable=[bool]$uv; nextAction='Run start.ps1 -Apply to prepare Python and deploy the backend.' } | ConvertTo-Json
    exit 0
}
$winget = Get-Command winget -ErrorAction SilentlyContinue
if (-not $winget) { throw 'Install Python 3.11 with the available Windows software installer, then run this command again.' }
& $winget.Source install --id Python.Python.3.11 --exact --source winget --silent --disable-interactivity
if ($LASTEXITCODE -ne 0) { throw "Python installation returned $LASTEXITCODE; continue after resolving this installer result." }
$Python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Python was installed; reopen the terminal and run this command again.' }
& $Python -X utf8 @arguments
exit $LASTEXITCODE
