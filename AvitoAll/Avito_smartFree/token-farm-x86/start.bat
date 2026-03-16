@echo off
REM Token Farm x86 - Quick Start Script for Windows

echo ==========================================
echo Token Farm x86 - Development Environment
echo ==========================================
echo.

REM Check if .env exists
if not exist .env (
    echo Creating .env file from template...
    copy .env.example .env
    echo.
    echo NOTE: Edit .env file to customize settings
    echo.
)

REM Start containers
echo Starting containers...
docker-compose up -d postgres redroid-x86-1 redroid-x86-2

echo.
echo Waiting for containers to start (10 seconds)...
timeout /t 10 /nobreak > nul

echo.
echo ==========================================
echo Container Status:
echo ==========================================
docker-compose ps

echo.
echo ==========================================
echo Connecting to containers via ADB...
echo ==========================================
adb connect localhost:5555
adb connect localhost:5556

echo.
echo ==========================================
echo Connected Devices:
echo ==========================================
adb devices

echo.
echo ==========================================
echo ✅ Setup Complete!
echo ==========================================
echo.
echo Next steps:
echo   1. Run tests: python test_x86_setup.py
echo   2. View logs: docker-compose logs -f
echo   3. Open shell: docker exec -it redroid-x86-1 sh
echo.
echo To stop: docker-compose down
echo.

pause
