@echo off
cd /d "%~dp0"
echo ============================================================
echo   Voice Typing - enable GPU acceleration (for large-v3)
echo ============================================================
echo This installs NVIDIA's CUDA math libraries (cuBLAS / cuDNN)
echo so the most accurate model (large-v3) can run fast on your
echo GPU. It's a one-time download of a few hundred MB.
echo.

if not exist "venv\Scripts\python.exe" (
  echo Please run setup.bat first, then run this again.
  pause
  exit /b 1
)

call venv\Scripts\python.exe -m pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
if errorlevel 1 (
  echo.
  echo [ERROR] Install failed. Check your internet connection and try again.
  pause
  exit /b 1
)

rem Re-enable the GPU in settings so the app tries it again next launch.
call venv\Scripts\python.exe -c "import json,os; c=json.load(open('config.json')) if os.path.exists('config.json') else {}; c['device']='cuda'; c['compute']='float16'; json.dump(c,open('config.json','w'),indent=2); print('GPU re-enabled in settings')"

echo.
echo ============================================================
echo   Done! Now open the app, set "Accuracy model" to large-v3,
echo   and reopen it. If the GPU still can't be used, the app
echo   automatically falls back to CPU so it always works.
echo ============================================================
echo.
pause
