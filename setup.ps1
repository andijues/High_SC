$ErrorActionPreference = 'Stop'
$appRoot = $PSScriptRoot
Set-Location -LiteralPath $appRoot
Write-Host 'High_SC - Installing local dependencies...'
$pythonExe = $null
if (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonExe = (& python -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
}
if (-not $pythonExe -and (Get-Command py -ErrorAction SilentlyContinue)) {
    $pythonExe = (& py -3 -c "import sys; print(sys.executable)" 2>$null | Select-Object -Last 1)
}
if (-not $pythonExe) { throw 'Python 3.11+ is required. Install Python, then run this file again.' }
& $pythonExe -c "import sys; assert sys.version_info >= (3,11), 'Python 3.11+ is required'"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11+ is required.' }
$venvPython = Join-Path $appRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $pythonExe -m venv (Join-Path $appRoot '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Failed to create the local Python environment.' }
}
$requirementsFile = Join-Path $appRoot 'requirements.lock.txt'
if (-not (Test-Path -LiteralPath $requirementsFile)) { $requirementsFile = Join-Path $appRoot 'requirements.txt' }
& $venvPython -m pip install -r $requirementsFile --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check your network or pip mirror, then retry.' }
& $venvPython -c "import fastapi,uvicorn,httpx,pydantic,pymupdf,multipart; print('High_SC is ready.')"
if ($LASTEXITCODE -ne 0) { throw 'Dependency verification failed.' }
