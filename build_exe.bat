@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Building VoiceTyping.exe  (takes several minutes)
echo ============================================================
echo.

if not exist "venv\Scripts\python.exe" (
  echo Setting up the environment first...
  call setup.bat
)

call venv\Scripts\python.exe -m pip install --upgrade pyinstaller
if errorlevel 1 ( echo [ERROR] could not install PyInstaller & pause & exit /b 1 )

call venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name "VoiceTyping" --icon "app.ico" ^
  --add-data "app.ico;." --add-data "logo.png;." --add-data "icon_small.png;." ^
  --collect-all customtkinter ^
  --collect-all faster_whisper ^
  --collect-all ctranslate2 ^
  --collect-all speech_recognition ^
  --collect-all language_tool_python ^
  --collect-all pyaudio ^
  --collect-submodules keyboard ^
  "voice_typing.py"

if errorlevel 1 ( echo. & echo [ERROR] Build failed - see messages above. & pause & exit /b 1 )

echo.
echo ============================================================
echo   Done!  Your app is here:   dist\VoiceTyping.exe
echo   - Double-click it to run (first launch downloads the model).
echo   - Upload dist\VoiceTyping.exe to your GitHub Release.
echo ============================================================
echo.
pause
endlocal
