@echo off
setlocal
cd /d "%~dp0\.." || exit /b 1

if not exist ".venv-win\Scripts\python.exe" (
  py -3 -m venv .venv-win
  if errorlevel 1 (
    python -m venv .venv-win
    if errorlevel 1 exit /b 1
  )
)

call ".venv-win\Scripts\activate.bat"
if errorlevel 1 exit /b 1

python -m pip install --upgrade pip
if errorlevel 1 exit /b 1

pip install -r windows\requirements.txt
if errorlevel 1 exit /b 1

echo.
echo Windows setup complete.
echo Run: scripts\run_windows.bat
