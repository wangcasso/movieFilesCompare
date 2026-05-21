@echo off
title Video Deduplication Tool

echo ========================================
echo    Video Deduplication Tool
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not detected!
    echo.
    echo Please install Python 3.6 or higher version
    echo Download: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

echo Python check passed
echo.
echo Starting program...
echo.

REM Run program
python "%~dp0video_dedup.py"

if %errorlevel% neq 0 (
    echo.
    echo Program execution error
    pause
)
