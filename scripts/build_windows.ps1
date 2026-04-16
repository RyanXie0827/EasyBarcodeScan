param(
    [ValidateSet("run", "build")]
    [string]$Mode = "build",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $RootDir ".venv_win"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

Set-Location $RootDir

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    Write-Host "Cannot find Python: $Python" -ForegroundColor Red
    Write-Host "Install Python 3 first or pass -Python with the executable path."
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "Creating virtual env: .venv_win"
    & $Python -m venv $VenvDir
}

$env:PYTHONPATH = Join-Path $RootDir "src"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

Write-Host "Installing Python dependencies ..."
& $VenvPython -m pip install -r requirements.txt

switch ($Mode) {
    "run" {
        Write-Host "Starting EasyBarcodeScan ..."
        & $VenvPython -m easybarcodescan
    }
    "build" {
        Write-Host "Cleaning old build artifacts ..."
        if (Test-Path "build") { Remove-Item -Recurse -Force "build" }
        if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }

        Write-Host "Building Windows EXE ..."
        & $VenvPython -m PyInstaller --noconfirm --clean packaging/pyinstaller/easybarcodescan.spec
        Write-Host "Done: dist\EasyBarcodeScan.exe"
    }
}
