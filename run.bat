@echo off
echo Universal Programmer - Starting...
echo.

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Python not found! Please install Python 3.8+ from python.org
    pause
    exit /b 1
)

REM Check dependencies
echo Checking dependencies...
pip install -r requirements.txt

REM Run app
echo Starting GUI...
python app.py

pause
