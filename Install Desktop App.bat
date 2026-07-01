@echo off
setlocal
cd /d "%~dp0"
set "FOLDER=%CD%"

echo ============================================================
echo   Voice Typing - installing the Desktop app icon
echo ============================================================
echo.

rem --- tidy up stray files (safe if they don't exist) ---
if exist "%FOLDER%\__synctest.txt" del /q "%FOLDER%\__synctest.txt" >nul 2>nul
if exist "%FOLDER%\__pycache__" rmdir /s /q "%FOLDER%\__pycache__" >nul 2>nul
rem --- remove the old generated icon now that we use app.ico ---
if exist "%FOLDER%\mic.ico" del /q "%FOLDER%\mic.ico" >nul 2>nul

rem --- pick the app icon (app.ico preferred, mic.ico as fallback) ---
set "ICON=%FOLDER%\app.ico"
if not exist "%ICON%" set "ICON=%FOLDER%\mic.ico"

rem --- create / refresh the "Voice Typing" shortcut on the Desktop ---
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $d=[Environment]::GetFolderPath('Desktop'); $l=$ws.CreateShortcut((Join-Path $d 'Voice Typing.lnk')); $l.TargetPath=(Join-Path $env:FOLDER 'run.bat'); $l.WorkingDirectory=$env:FOLDER; if(Test-Path $env:ICON){$l.IconLocation=$env:ICON}; $l.Description='Voice Typing - press Alt + Up to dictate anywhere'; $l.WindowStyle=1; $l.Save(); Write-Host ('Created: ' + (Join-Path $d 'Voice Typing.lnk'))"

if errorlevel 1 (
  echo.
  echo [ERROR] Could not create the shortcut.
  echo You can still start the app by double-clicking run.bat in this folder.
)

rem --- refresh Windows icon cache so the new logo shows right away ---
ie4uinit.exe -show >nul 2>nul

if /I "%~1"=="auto" goto :end
echo.
echo Done! The "Voice Typing" icon on your Desktop now uses your new logo.
echo Double-click it any time to start dictating.
echo.
pause
:end
endlocal
