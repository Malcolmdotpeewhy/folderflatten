@echo off
echo ========================================
echo   Folder Flattener GUI - Quick Launch
echo ========================================
echo.
echo Starting Folder Flattener application...
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3.7+ and try again
    pause
    exit /b 1
)

REM Try to install optional drag-and-drop support
echo Installing optional drag-and-drop support...
pip install tkinterdnd2 >nul 2>&1
if %errorlevel% neq 0 (
    echo Note: Could not install drag-and-drop support
    echo The application will still work with the Browse button
    echo.
)

REM Launch the application
echo Launching Folder Flattener GUI...
python "%~dp0folder_flattener_gui.py"

if %errorlevel% neq 0 (
    echo.
    echo Application encountered an error.
    pause
)
