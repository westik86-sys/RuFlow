@echo off
setlocal
cd /d "%~dp0\.." || exit /b 1

call scripts\setup_windows.bat
if errorlevel 1 exit /b 1

call ".venv-win\Scripts\activate.bat"
if errorlevel 1 exit /b 1

python -m pip install -r windows\requirements-build.txt
if errorlevel 1 exit /b 1

python -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --noconsole ^
  --name RuFlow ^
  --icon "%CD%\installer\assets\ruflow.ico" ^
  --distpath dist\windows ^
  --workpath build\windows\app ^
  --specpath build\windows\spec ^
  --paths . ^
  --copy-metadata onnx-asr ^
  --copy-metadata onnxruntime ^
  --collect-data onnx_asr ^
  --collect-binaries onnxruntime ^
  --hidden-import asr.runner ^
  --hidden-import pystray._win32 ^
  --hidden-import PIL.Image ^
  --hidden-import PIL.ImageDraw ^
  --hidden-import PIL.ImageFont ^
  windows\ruflow_windows.py
if errorlevel 1 exit /b 1

echo.
echo Built:
echo   dist\windows\RuFlow\RuFlow.exe
