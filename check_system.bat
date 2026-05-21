@echo off
title System Check

echo ========================================
echo   System Check
echo ========================================
echo.

echo [1/3] Checking Python...
python --version 2>&1 | findstr "Python" >nul
if %errorlevel% equ 0 (
    echo     Python: OK
    python --version
) else (
    echo     Python: NOT FOUND
    echo     Please install Python first!
)
echo.

echo [2/3] Checking main program...
if exist "video_dedup.py" (
    echo     video_dedup.py: FOUND
) else (
    echo     video_dedup.py: MISSING
)
echo.

echo [3/3] Checking configuration...
if exist "config.json" (
    echo     config.json: FOUND
) else (
    echo     config.json: MISSING
)
echo.

echo ========================================
echo   System check complete!
echo ========================================
echo.
echo To start the program:
echo   1. Double-click: StartProgram.vbs
echo   2. Or use command: python video_dedup.py
echo.
pause
