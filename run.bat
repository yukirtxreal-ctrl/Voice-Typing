@echo off
cd /d "%~dp0"

set "PYW=venv\Scripts\pythonw.exe"
set "PY=venv\Scripts\python.exe"

rem No environment yet -> full setup (installs everything, downloads best model).
if not exist "%PYW%" (
  echo First-time setup - installing the app. Please wait...
  call setup.bat
  goto launch
)

rem Environment exists -> make sure all (possibly new) dependencies are present.
"%PY%" -c "import customtkinter, faster_whisper, PIL, speech_recognition, keyboard, numpy" 1>nul 2>nul
if errorlevel 1 (
  echo Updating components...
  call setup.bat
)

:launch
rem Launch the app windowed with NO console, through the auto-reload watcher.
start "" "%PYW%" run_app.py
