@echo off
setlocal
set "PYTHON_PATH=%~dp0.venv\Scripts\python.exe"
if not "%~1"=="" set "PYTHON_PATH=%~1"
"%PYTHON_PATH%" "%~dp0build_exe.py"
exit /b %ERRORLEVEL%
