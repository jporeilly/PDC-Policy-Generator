@echo off
REM Policy Generator - Windows launcher (double-click or run from cmd).
REM Forwards any args to run.ps1, e.g.:  run.bat -Port 8081
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
