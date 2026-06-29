@echo off
setlocal
cd /d "%~dp0"
set "FOLDER=%CD%"

echo ============================================================
echo   Voice Typing - start automatically with Windows
echo ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws=New-Object -ComObject WScript.Shell; $sf=[Environment]::GetFolderPath('Startup'); $l=$ws.CreateShortcut((Join-Path $sf 'Voice Typing.lnk')); $l.TargetPath=(Join-Path $env:FOLDER 'run.bat'); $l.WorkingDirectory=$env:FOLDER; $ic=(Join-Path $env:FOLDER 'app.ico'); if(Test-Path $ic){$l.IconLocation=$ic}; $l.WindowStyle=7; $l.Description='Voice Typing'; $l.Save(); Write-Host ('Added to startup: ' + (Join-Path $sf 'Voice Typing.lnk'))"

echo.
echo Done - Voice Typing will launch when Windows starts.
echo.
echo To turn this OFF later: press Win+R, type  shell:startup  and press Enter,
echo then delete the "Voice Typing" shortcut in that folder.
echo.
pause
endlocal
