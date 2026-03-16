@echo off
echo ========================================
echo   Setup Device as Google Pixel 6
echo ========================================
echo.

cd /d %~dp0..

REM Check if Redroid is running
docker ps | findstr avito-redroid >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Redroid is not running
    echo.
    echo Please run 02_start_redroid.bat first
    echo.
    pause
    exit /b 1
)

echo [1/4] Connecting to Redroid...
docker exec avito-redroid getprop ro.product.model >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Cannot connect to Redroid
    echo.
    echo Wait a few more seconds for Redroid to boot
    echo Then run this script again
    echo.
    pause
    exit /b 1
)
echo [OK] Connected

echo.
echo [2/4] Current device info:
docker exec avito-redroid sh -c "echo 'Model: '$(getprop ro.product.model)"
docker exec avito-redroid sh -c "echo 'Manufacturer: '$(getprop ro.product.manufacturer)"
docker exec avito-redroid sh -c "echo 'Brand: '$(getprop ro.product.brand)"

echo.
echo [3/4] Applying Pixel 6 properties...

REM Copy build.prop to container
docker cp config\build.prop.pixel6 avito-redroid:/tmp/build.prop.new

REM Apply build.prop (need to remount /system as rw)
docker exec avito-redroid sh -c "mount -o rw,remount /system"
docker exec avito-redroid sh -c "cp /tmp/build.prop.new /system/build.prop"
docker exec avito-redroid sh -c "chmod 644 /system/build.prop"

if %errorlevel% neq 0 (
    echo [X] Failed to apply build.prop
    echo.
    echo This is expected - build.prop is read-only in Redroid
    echo We'll use setprop instead for runtime changes
    echo.
)

echo.
echo [4/4] Setting runtime properties...

REM Set properties at runtime
docker exec avito-redroid setprop ro.product.model "Pixel 6"
docker exec avito-redroid setprop ro.product.manufacturer "Google"
docker exec avito-redroid setprop ro.product.brand "google"
docker exec avito-redroid setprop ro.product.device "oriole"
docker exec avito-redroid setprop ro.product.name "oriole"
docker exec avito-redroid setprop ro.build.fingerprint "google/oriole/oriole:13/TQ3A.230901.001/10750268:user/release-keys"

echo.
echo ========================================
echo   Device configured!
echo ========================================
echo.
echo New device info:
docker exec avito-redroid sh -c "echo 'Model: '$(getprop ro.product.model)"
docker exec avito-redroid sh -c "echo 'Manufacturer: '$(getprop ro.product.manufacturer)"
docker exec avito-redroid sh -c "echo 'Brand: '$(getprop ro.product.brand)"
docker exec avito-redroid sh -c "echo 'Device: '$(getprop ro.product.device)"

echo.
echo NOTE: Properties set with setprop are temporary
echo They will reset after container restart
echo.
echo For permanent changes, rebuild container with:
echo   docker-compose down -v
echo   docker-compose up -d
echo.
echo Next step: Run 04_install_frida.bat
echo.
pause
