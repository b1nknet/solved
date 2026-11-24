@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "PYTHON_CMD=python.exe"
where py.exe >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py.exe -3"

%PYTHON_CMD% "%~dp0organize_problems.py"
if not "%errorlevel%"=="0" exit /b %errorlevel%

%PYTHON_CMD% "%~dp0update_readme.py"
exit /b %errorlevel%
