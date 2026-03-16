@echo off
REM ========================================
REM  Mask Android Emulator as Google Pixel 6
REM ========================================
REM
REM This changes Build properties so Avito sees:
REM   "Google Pixel 6" instead of "sdk_gphone64_x86_64"
REM
REM IMPORTANT: Changes are temporary (RAM only)
REM Will reset after emulator reboot
REM ========================================

echo.
echo ========================================
echo  Device Masking: Pixel 6
echo ========================================
echo.

REM Check ADB connection
adb devices | findstr /R "device$" >nul
if errorlevel 1 (
    echo ERROR: No Android device connected!
    echo Please start the emulator first: 02_start_emulator.bat
    pause
    exit /b 1
)

echo [1/4] Getting root access...
adb root
if errorlevel 1 (
    echo.
    echo ERROR: Cannot get root access!
    echo.
    echo This usually means you are using Play Store image.
    echo You need Google APIs image (without Play Store) for root access.
    echo.
    echo To fix:
    echo   1. Delete current AVD
    echo   2. Create new AVD with system image:
    echo      android-33;google_apis;x86_64 (NOT google_apis_playstore)
    echo.
    pause
    exit /b 1
)

timeout /t 2 /nobreak >nul

echo Waiting for device to restart in root mode...
adb wait-for-device
timeout /t 3 /nobreak >nul

echo.
echo [2/4] Setting Pixel 6 Build properties...
echo.

REM Set Build properties
adb shell "setprop ro.product.model 'Pixel 6'" 2>nul
echo   - Model: Pixel 6

adb shell "setprop ro.product.manufacturer Google" 2>nul
echo   - Manufacturer: Google

adb shell "setprop ro.product.brand google" 2>nul
echo   - Brand: google

adb shell "setprop ro.product.name oriole" 2>nul
echo   - Product Name: oriole

adb shell "setprop ro.product.device oriole" 2>nul
echo   - Device: oriole

adb shell "setprop ro.build.fingerprint google/oriole/oriole:13/TQ3A.230901.001/10750268:user/release-keys" 2>nul
echo   - Build Fingerprint: google/oriole/...

echo.
echo [3/4] Verifying changes...
echo.

for /f "delims=" %%i in ('adb shell "getprop ro.product.model" 2^>nul') do set MODEL=%%i
for /f "delims=" %%i in ('adb shell "getprop ro.product.manufacturer" 2^>nul') do set MANUFACTURER=%%i
for /f "delims=" %%i in ('adb shell "getprop ro.product.brand" 2^>nul') do set BRAND=%%i

echo Current device info:
echo   Model:        %MODEL%
echo   Manufacturer: %MANUFACTURER%
echo   Brand:        %BRAND%

echo.
echo [4/4] Verification complete!
echo.

REM Check if masking was successful
echo %MODEL% | findstr /C:"Pixel 6" >nul
if errorlevel 1 (
    echo ========================================
    echo  WARNING: Masking may have failed!
    echo.
    echo  Model is still: %MODEL%
    echo  Expected: Pixel 6
    echo.
    echo  Try running this script again.
    echo ========================================
) else (
    echo ========================================
    echo  SUCCESS: Device masked as Pixel 6
    echo.
    echo  Avito will now see:
    echo    - Device: Google Pixel 6
    echo    - NO emulator detection warnings
    echo.
    echo  IMPORTANT:
    echo    - Masking is temporary (RAM only)
    echo    - Will reset after emulator reboot
    echo    - Run this script again after reboot
    echo.
    echo  Next step:
    echo    04_install_frida.bat
    echo ========================================
)

echo.
pause
