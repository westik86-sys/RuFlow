@echo off
setlocal
cd /d "%~dp0\.." || exit /b 1

call scripts\build_windows_app.bat
if errorlevel 1 exit /b 1

call ".venv-win\Scripts\activate.bat"
if errorlevel 1 exit /b 1

dist\windows\RuFlow\RuFlow.exe --download-model --model-dir dist\windows\RuFlow\models\gigaam-v3-e2e-rnnt
if errorlevel 1 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\sign_windows.ps1 -Path dist\windows\RuFlow\RuFlow.exe
if errorlevel 1 exit /b 1

set "ISCC=ISCC.exe"
where ISCC.exe >nul 2>nul
if errorlevel 1 (
  if exist "%LocalAppData%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LocalAppData%\Programs\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
)

"%ISCC%" installer\RuFlow.iss
if errorlevel 1 (
  echo.
  echo Inno Setup compiler was not found or failed.
  echo Install Inno Setup 6, then rerun scripts\build_windows_release.bat.
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\sign_windows.ps1 -Path dist\windows\RuFlowSetup-x64.exe
if errorlevel 1 exit /b 1

powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "if (Test-Path dist\windows\RuFlow-portable-x64.zip) { Remove-Item dist\windows\RuFlow-portable-x64.zip -Force }; Compress-Archive -Path dist\windows\RuFlow -DestinationPath dist\windows\RuFlow-portable-x64.zip"
if errorlevel 1 exit /b 1

echo.
echo Release artifacts:
echo   dist\windows\RuFlow\RuFlow.exe
echo   dist\windows\RuFlowSetup-x64.exe
echo   dist\windows\RuFlow-portable-x64.zip
