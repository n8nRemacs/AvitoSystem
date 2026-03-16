@echo off
echo ========================================
echo   Installing Avito APK
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

REM Check if APK exists
if not exist "avito.apk" (
    echo [X] avito.apk not found
    echo.
    echo Please download Avito APK and place it here:
    echo %cd%\avito.apk
    echo.
    echo Download from:
    echo   https://apkpure.com/avito/com.avito.android
    echo.
    echo Or copy from:
    echo   ..\avito.apk
    echo.
    choice /C YN /M "Copy from parent directory"
    if errorlevel 2 goto :no_copy
    if errorlevel 1 goto :copy_apk
)

goto :install

:copy_apk
if exist "..\avito.apk" (
    echo Copying APK...
    copy "..\avito.apk" "avito.apk"
    goto :install
) else (
    echo [X] APK not found in parent directory
    pause
    exit /b 1
)

:no_copy
pause
exit /b 1

:install
echo [1/3] Checking APK...
for %%A in (avito.apk) do set APK_SIZE=%%~zA
set /a APK_SIZE_MB=%APK_SIZE% / 1048576

if %APK_SIZE_MB% LSS 50 (
    echo [!] Warning: APK is only %APK_SIZE_MB% MB
    echo    Expected size: 150-250 MB
    echo.
    choice /C YN /M "Continue anyway"
    if errorlevel 2 exit /b 1
)

echo [OK] APK size: %APK_SIZE_MB% MB

echo.
echo [2/3] Installing Avito to Redroid...
docker exec avito-redroid pm list packages | findstr com.avito.android >nul 2>&1
if %errorlevel% equ 0 (
    echo [!] Avito is already installed
    choice /C YN /M "Reinstall"
    if errorlevel 2 goto :skip_install
)

REM Copy APK to container and install
docker cp avito.apk avito-redroid:/tmp/avito.apk
docker exec avito-redroid pm install -r /tmp/avito.apk

if %errorlevel% neq 0 (
    echo [X] Failed to install Avito
    echo.
    echo Check APK is valid:
    echo   - Download latest version
    echo   - File not corrupted
    echo   - Correct architecture (x86_64)
    echo.
    pause
    exit /b 1
)

docker exec avito-redroid rm /tmp/avito.apk

:skip_install
echo [OK] Installed

echo.
echo [3/3] Verifying installation...
docker exec avito-redroid pm list packages | findstr com.avito.android
docker exec avito-redroid cmd package dump com.avito.android | findstr "versionName"

echo.
echo ========================================
echo   Avito installed successfully!
echo ========================================
echo.
echo Package: com.avito.android
echo.
echo Launch Avito:
echo   docker exec avito-redroid am start -n com.avito.android/.Launcher
echo.
echo Next step:
echo   1. View device screen with scrcpy or VNC
echo   2. Authorize in Avito manually
echo   3. Run 06_extract_tokens.bat
echo.
pause
