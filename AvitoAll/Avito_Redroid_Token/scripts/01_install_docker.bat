@echo off
echo ========================================
echo   Docker Installation Check
echo ========================================
echo.

REM Check if Docker is installed
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Docker is NOT installed
    echo.
    echo Please install Docker Desktop for Windows:
    echo https://www.docker.com/products/docker-desktop/
    echo.
    echo Installation steps:
    echo 1. Download Docker Desktop
    echo 2. Run installer
    echo 3. Enable WSL 2 backend
    echo 4. Restart computer
    echo 5. Run this script again
    echo.
    pause
    exit /b 1
)

echo [OK] Docker is installed
docker --version

echo.
REM Check if Docker Compose is installed
docker-compose --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Docker Compose is NOT installed
    echo.
    echo Docker Compose should be included with Docker Desktop.
    echo Try reinstalling Docker Desktop.
    echo.
    pause
    exit /b 1
)

echo [OK] Docker Compose is installed
docker-compose --version

echo.
REM Check if Docker daemon is running
docker ps >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Docker daemon is NOT running
    echo.
    echo Please start Docker Desktop from Start Menu
    echo Wait for it to fully start (green icon in system tray)
    echo Then run this script again
    echo.
    pause
    exit /b 1
)

echo [OK] Docker daemon is running

echo.
echo ========================================
echo   Docker is ready!
echo ========================================
echo.
echo Next step: Run 02_start_redroid.bat
echo.
pause
