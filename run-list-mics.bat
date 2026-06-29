@echo off
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
  echo Virtual environment not found - running setup first...
  call setup.bat
)

call venv\Scripts\python.exe voice_typing.py --list-mics
pause
