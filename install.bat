@echo off
REM ============================================================
REM  First-time setup for Auto PhotoEditor
REM  Installs Python dependencies (opencv-python, numpy, pillow)
REM  into the SAME Python that run_gui.bat will use.
REM ============================================================

echo.
echo ==== Auto PhotoEditor - first time install ====
echo.

REM Prefer 'python' (commonly the interpreter with pip + packages),
REM fall back to the 'py' launcher.
where python >nul 2>&1
if %errorlevel%==0 (
    set PYCMD=python
) else (
    set PYCMD=py
)

echo Using interpreter:
%PYCMD% --version
if errorlevel 1 (
    echo.
    echo ERROR: Python was not found on your PATH.
    echo Install Python 3 from https://www.python.org/downloads/
    echo and be sure to check "Add Python to PATH" during install.
    echo.
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
%PYCMD% -m pip install --upgrade pip
%PYCMD% -m pip install -r "%~dp0requirements.txt"

if errorlevel 1 (
    echo.
    echo ERROR: Dependency install failed. See messages above.
    pause
    exit /b 1
)

echo.
echo ==== Done! You can now double-click run_gui.bat to start. ====
echo.
pause
