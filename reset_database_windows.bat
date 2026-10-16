@echo off
REM Double-click to rebuild the database with fresh demo data.
cd /d "%~dp0"
set RUNPY=venv\Scripts\python.exe
if not exist "venv\Scripts\python.exe" (
  set RUNPY=python
  where py >nul 2>nul && set RUNPY=py
)
"%RUNPY%" seed.py
pause
