@echo off
title Build EXE for Video Deduplication Tool

echo ========================================
echo    Build EXE Package
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not detected!
    echo.
    pause
    exit /b 1
)

echo Python check passed
echo.

REM Check if PyInstaller is installed
pip show pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Installing PyInstaller...
    pip install pyinstaller
    if %errorlevel% neq 0 (
        echo.
        echo Failed to install PyInstaller
        pause
        exit /b 1
    )
)

echo PyInstaller ready
echo.
echo Building EXE...
echo.

REM Build EXE
pyinstaller --onefile --windowed --name="VideoDedup" --icon=NONE "%~dp0video_dedup.py"

if %errorlevel% equ 0 (
    echo.
    echo Build successful!
    echo.
    echo EXE location: dist\VideoDedup.exe
    echo.
    echo You can copy this exe file to any Windows computer.
) else (
    echo.
    echo Build failed
)

echo.
pause
