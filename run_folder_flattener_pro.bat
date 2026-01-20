@echo off
echo ===============================================
echo   🗂️ Folder Flattener Pro - Quick Launch 🚀
echo ===============================================
echo.
echo Starting the enhanced Folder Flattener Pro...
echo.

REM Check if Python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Error: Python is not installed or not in PATH
    echo Please install Python 3.8+ and try again
    echo Download from: https://python.org/downloads/
    pause
    exit /b 1
)

echo ✅ Python detected, checking version...
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo    Version: %PYTHON_VERSION%

REM Try to install optional drag-and-drop support
echo.
echo 📦 Installing optional enhancements...
echo    This may take a moment...

pip install tkinterdnd2 >nul 2>&1
if %errorlevel% equ 0 (
    echo ✅ Drag ^& drop support installed successfully
) else (
    echo ⚠️  Could not install drag ^& drop support
    echo    The application will work with the Browse button
)

echo.
echo 🚀 Launching Folder Flattener Pro...
echo    Close this window to exit the application
echo.

REM Launch the enhanced application
python "%~dp0folder_flattener_gui.py"

if %errorlevel% neq 0 (
    echo.
    echo ❌ Application encountered an error
    echo Check the log file for details
    pause
) else (
    echo.
    echo ✅ Application closed successfully
)

echo.
echo Press any key to exit...
pause >nul
