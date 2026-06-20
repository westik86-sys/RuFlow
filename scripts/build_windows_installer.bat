@echo off
setlocal
cd /d "%~dp0\.." || exit /b 1

call scripts\build_windows_release.bat
