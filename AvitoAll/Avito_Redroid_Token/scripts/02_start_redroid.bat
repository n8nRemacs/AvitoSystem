@echo off
echo ========================================
echo   Starting Redroid Container
echo ========================================
echo.

cd /d %~dp0..

REM Check if container is already running
docker ps | findstr avito-redroid >nul 2>&1
if %errorlevel% equ 0 (
    echo [!] Redroid is already running
    echo.
    choice /C YN /M "Do you want to restart it"
    if errorlevel 2 goto :skip_restart
    if errorlevel 1 goto :restart
)

goto :start

:restart
echo.
echo [1/3] Stopping existing container...
docker-compose down
timeout /t 3 >nul

:start
echo.
echo [2/3] Starting Redroid (first start may take 2-3 minutes)...
docker-compose up -d

if %errorlevel% neq 0 (
    echo.
    echo [X] Failed to start Redroid
    echo.
    echo Check Docker Desktop is running
    echo Check docker-compose.yml is correct
    echo.
    pause
    exit /b 1
)

echo.
echo [3/3] Waiting for Redroid to boot...
timeout /t 10 >nul

REM Wait for ADB to be ready
set retry=0
:wait_adb
set /a retry+=1
if %retry% gtr 30 (
    echo.
    echo [X] Timeout waiting for Redroid to start
    echo.
    echo Check logs: docker logs avito-redroid
    echo.
    pause
    exit /b 1
)

docker exec avito-redroid getprop sys.boot_completed 2>nul | findstr "1" >nul 2>&1
if %errorlevel% neq 0 (
    echo Waiting for boot... (%retry%/30)
    timeout /t 2 >nul
    goto :wait_adb
)

:skip_restart
echo.
echo ========================================
echo   Redroid is running!
echo ========================================
echo.
echo Container: avito-redroid
echo ADB Port: 127.0.0.1:5555
echo VNC Port: 127.0.0.1:5900
echo.
echo Connect ADB:
echo   adb connect 127.0.0.1:5555
echo.
echo View logs:
echo   docker logs avito-redroid -f
echo.
echo Next step: Run 03_setup_device.bat
echo.
pause
