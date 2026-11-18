param([string]$Python = 'python', [switch]$NoShortcut)
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Laptop Remote requires Windows 10 or 11.' }
$project = $PSScriptRoot
& $Python -c "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or newer is required'"
if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.11+ and add it to PATH, or pass -Python with its executable path.' }
$venv = Join-Path $project '.venv'
$pythonExe = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venv)) {
    & $Python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
if (-not (Test-Path -LiteralPath $pythonExe)) { throw 'The .venv folder is incomplete. Remove it and run setup again.' }
& $pythonExe -c "import sys; assert sys.version_info >= (3, 11), 'The existing environment needs Python 3.11 or newer'"
if ($LASTEXITCODE -ne 0) { throw 'The existing Python environment is unsupported.' }
& $pythonExe -m pip --disable-pip-version-check --require-virtualenv install -r (Join-Path $project 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. See the pip error above.' }
if (-not $NoShortcut) {
    & $pythonExe (Join-Path $project 'install_shortcut.py')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the desktop shortcut.' }
}
if ($NoShortcut) { Write-Host 'Setup complete.' }
else { Write-Host 'Setup complete. Open Laptop Remote from your desktop.' }
