@echo off
REM Launch the Photo Culler GUI using the same interpreter install.bat used.
REM Double-click this file instead of the .py so the right Python is used.

where python >nul 2>&1
if %errorlevel%==0 (
    set PYCMD=python
) else (
    set PYCMD=py
)

%PYCMD% "%~dp0cull_photos_gui.py"

REM If it crashed, keep the window open so the error is readable.
if errorlevel 1 (
    echo.
    echo The program exited with an error. If you see "No module named 'cv2'",
    echo run install.bat first.
    echo.
    pause
)
