@echo off
setlocal
"%~dp0.venv\Scripts\pythonw.exe" "%~dp0gui.py"
exit /b %ERRORLEVEL%
