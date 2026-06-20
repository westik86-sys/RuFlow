@echo off
setlocal
cd /d "%~dp0\.." || exit /b 1

if not exist ".venv-win\Scripts\python.exe" (
  call scripts\setup_windows.bat
  if errorlevel 1 exit /b 1
)

".venv-win\Scripts\python.exe" windows\ruflow_windows.py %*
exit /b %errorlevel%
