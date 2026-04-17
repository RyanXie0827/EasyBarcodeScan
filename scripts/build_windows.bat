@echo off
setlocal

set MODE=%~1
if "%MODE%"=="" set MODE=build

set PYTHON_EXE=%~2
if "%PYTHON_EXE%"=="" set PYTHON_EXE=python

set RUNTIME_FLAG=-UseSystemPython
if /I "%~2"=="system" (
    set PYTHON_EXE=python
    set RUNTIME_FLAG=-UseSystemPython
)
if /I "%~3"=="system" set RUNTIME_FLAG=-UseSystemPython

if /I "%~2"=="venv" (
    set PYTHON_EXE=python
    set RUNTIME_FLAG=-UseVenvPython
)
if /I "%~3"=="venv" set RUNTIME_FLAG=-UseVenvPython

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" -Mode "%MODE%" -Python "%PYTHON_EXE%" %RUNTIME_FLAG%
exit /b %ERRORLEVEL%
