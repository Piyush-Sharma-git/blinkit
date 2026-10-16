@echo off
REM ==================================================================
REM  start_windows.bat - double-click this file to run the website.
REM  First run: creates venv, installs libraries, builds the database.
REM  Later runs: just starts the website.
REM ==================================================================
cd /d "%~dp0"
title Blinkit Sales Portal
echo ==================================================
echo    Blinkit Sales Portal - starting up
echo ==================================================
echo.

REM --- Refuse to run from WhatsApp / app-store private folders ---
echo "%CD%" | find /i "\AppData\Local\Packages\" >nul
if %errorlevel%==0 goto badplace
echo "%CD%" | find /i "\AppData\Local\Temp\" >nul
if %errorlevel%==0 goto badplace

set PY=python
where py >nul 2>nul
if %errorlevel%==0 set PY=py

%PY% --version
if errorlevel 1 goto nopython

REM --- Project environment (venv). Rebuilt if a previous attempt broke. ---
set RUNPY=venv\Scripts\python.exe
if exist "venv\Scripts\pip.exe" goto haveenv
if exist "venv" rmdir /s /q "venv"
echo Creating the project environment - first run only...
%PY% -m venv venv
if exist "venv\Scripts\pip.exe" goto haveenv
echo.
echo Could not create a separate environment. Using your main Python instead.
if exist "venv" rmdir /s /q "venv"
set RUNPY=%PY%

:haveenv
echo Checking libraries - the first run takes 1 to 2 minutes...
"%RUNPY%" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 goto fail

if not exist ".env" copy ".env.example" ".env" >nul

echo Checking the database...
"%RUNPY%" seed.py --ensure
if errorlevel 1 goto fail

echo.
echo ==================================================
echo  Website is starting at  http://127.0.0.1:5000
echo  Staff login:            http://127.0.0.1:5000/admin/login
echo  KEEP THIS WINDOW OPEN. Close it to stop the website.
echo ==================================================
echo.
start "" /min powershell -NoProfile -Command "Start-Sleep 4; Start-Process 'http://127.0.0.1:5000'"
"%RUNPY%" app.py
echo.
echo The website has stopped.
pause
exit /b 0

:badplace
echo This folder is inside a protected app folder - for example WhatsApp storage
echo or a zip file that was opened without extracting. Windows blocks installs here.
echo.
echo   1. Create a folder:  C:\projects
echo   2. Copy blinkit_project.zip into C:\projects
echo   3. Right-click the zip, choose Extract All, then Extract
echo   4. Open C:\projects\blinkit_project and double-click start_windows again
echo.
echo Current folder: %CD%
pause
exit /b 1

:nopython
echo.
echo Python was not found.
echo Reinstall Python 3.13 from python.org and TICK the box "Add python.exe to PATH".
pause
exit /b 1

:fail
echo.
echo Something went wrong. Take a screenshot of this window and send it.
pause
exit /b 1
