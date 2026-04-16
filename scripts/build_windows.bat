@echo off
setlocal

set MODE=%~1
if "%MODE%"=="" set MODE=build

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_windows.ps1" -Mode "%MODE%"
exit /b %ERRORLEVEL%
