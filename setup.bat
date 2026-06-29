@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Voice Typing - Setup
echo ============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python was not found.
  echo.
  echo Please install Python 3.9 or newer from:
  echo     https://www.python.org/downloads/
  echo IMPORTANT: during install, tick "Add Python to PATH".
  echo Then run this setup.bat again.
  echo.
  pause
  exit /b 1
)

echo Creating a private virtual environment (folder "venv")...
python -m venv venv
if errorlevel 1 (
  echo [ERROR] Could not create the virtual environment.
  pause
  exit /b 1
)

echo Upgrading pip...
call venv\Scripts\python.exe -m pip install --upgrade pip

echo.
echo Installing dependencies (this can take a few minutes)...
call venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
  echo [ERROR] Installing dependencies failed.
  echo If PyAudio failed to install, try:  pip install pipwin  then  pipwin install pyaudio
  pause
  exit /b 1
)

echo.
echo Detecting your hardware (GPU/CPU) and downloading the best model...
echo (If you have an NVIDIA GPU this grabs the most accurate model; this can be
echo  a larger one-time download. On CPU it grabs a fast, light model.)
call venv\Scripts\python.exe firstrun_setup.py

echo.
echo Putting a "Voice Typing" icon on your Desktop...
call "Install Desktop App.bat" auto

echo.
echo ============================================================
echo   Setup complete!
echo   - A "Voice Typing" icon is now on your Desktop - double-click it.
echo   - Or double-click  run.bat            to start dictating.
echo   - Double-click     run-list-mics.bat  to see your microphones.
echo ============================================================
echo.
pause
