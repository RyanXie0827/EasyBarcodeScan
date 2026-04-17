param(
    [ValidateSet("run", "build")]
    [string]$Mode = "build",
    [string]$Python = "python",
    [switch]$UseSystemPython,
    [switch]$UseVenvPython
)

$ErrorActionPreference = "Stop"

function Invoke-NativeCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Executable,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$DisplayName
    )

    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$DisplayName failed with exit code $LASTEXITCODE."
    }
}

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$VenvDir = Join-Path $RootDir ".venv_win"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$WindowsDistDir = Join-Path $RootDir "dist\windows"
$WindowsBuildDir = Join-Path $RootDir "build\windows"
$PyInstallerCacheDir = if ($env:PYINSTALLER_CONFIG_DIR) { $env:PYINSTALLER_CONFIG_DIR } else { Join-Path $RootDir ".pyinstaller\windows" }
$VersionSource = Join-Path $RootDir "src\easybarcodescan\version.py"
$VersionMatch = [regex]::Match((Get-Content $VersionSource -Raw), 'APP_VERSION\s*=\s*"([^"]+)"')
if (-not $VersionMatch.Success) {
    Write-Host "Cannot read APP_VERSION from $VersionSource" -ForegroundColor Red
    exit 1
}
$AppVersion = $VersionMatch.Groups[1].Value
$VersionSuffix = "v$AppVersion"
$VersionedExePath = Join-Path $WindowsDistDir "EasyBarcodeScan-$VersionSuffix.exe"

Set-Location $RootDir

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    Write-Host "Cannot find Python: $Python" -ForegroundColor Red
    Write-Host "Install Python 3 first or pass -Python with the executable path."
    exit 1
}

if ($UseSystemPython -and $UseVenvPython) {
    Write-Host "Cannot use both -UseSystemPython and -UseVenvPython at the same time." -ForegroundColor Red
    exit 1
}

$UseSystemRuntime = $true
if ($UseVenvPython) {
    $UseSystemRuntime = $false
}
elseif ($PSBoundParameters.ContainsKey("UseSystemPython")) {
    $UseSystemRuntime = [bool]$UseSystemPython
}

if ($UseSystemRuntime) {
    $RuntimePython = $Python
    Write-Host "Using system Python: $RuntimePython"
}
else {
    if (-not (Test-Path $VenvPython)) {
        Write-Host "Creating virtual env: .venv_win"
        Invoke-NativeCommand -Executable $Python -Arguments @("-m", "venv", $VenvDir) -DisplayName "Creating virtual environment"
    }
    $RuntimePython = $VenvPython
}

$env:PYTHONPATH = Join-Path $RootDir "src"
$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"
$env:PYINSTALLER_CONFIG_DIR = $PyInstallerCacheDir

Write-Host "Installing Python dependencies ..."
Invoke-NativeCommand -Executable $RuntimePython -Arguments @("-m", "pip", "install", "-r", "requirements.txt") -DisplayName "Installing Python dependencies"

switch ($Mode) {
    "run" {
        Write-Host "Starting EasyBarcodeScan ..."
        Invoke-NativeCommand -Executable $RuntimePython -Arguments @("-m", "easybarcodescan") -DisplayName "Starting EasyBarcodeScan"
    }
    "build" {
        Write-Host "Cleaning old build artifacts ..."
        if (Test-Path $WindowsBuildDir) { Remove-Item -Recurse -Force $WindowsBuildDir }
        if (Test-Path $WindowsDistDir) { Remove-Item -Recurse -Force $WindowsDistDir }
        if (Test-Path $PyInstallerCacheDir) { Remove-Item -Recurse -Force $PyInstallerCacheDir }

        New-Item -ItemType Directory -Force -Path $WindowsBuildDir | Out-Null
        New-Item -ItemType Directory -Force -Path $WindowsDistDir | Out-Null
        New-Item -ItemType Directory -Force -Path $PyInstallerCacheDir | Out-Null

        Write-Host "Building Windows EXE ..."
        Invoke-NativeCommand -Executable $RuntimePython -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", $WindowsDistDir, "--workpath", $WindowsBuildDir, "packaging/pyinstaller/easybarcodescan.spec") -DisplayName "Building Windows EXE with PyInstaller"
        $DefaultExePath = Join-Path $WindowsDistDir "EasyBarcodeScan.exe"
        if (-not (Test-Path $DefaultExePath)) {
            throw "PyInstaller completed but '$DefaultExePath' was not generated."
        }
        Move-Item -Force $DefaultExePath $VersionedExePath
        Write-Host "Done: dist\windows\EasyBarcodeScan-$VersionSuffix.exe"
    }
}
