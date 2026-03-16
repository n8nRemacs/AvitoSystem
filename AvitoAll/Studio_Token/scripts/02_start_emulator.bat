@echo off
REM ========================================
REM  Start Android Emulator for Token Extraction
REM ========================================

echo.
echo ========================================
echo  Starting Android Emulator
echo ========================================
echo.

REM Configuration
SET AVD_NAME=avito_token_emulator

REM Find Android SDK
if not defined ANDROID_HOME (
    if exist "%LOCALAPPDATA%\Android\Sdk" (
        SET ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk
    ) else (
        echo ERROR: Android SDK not found!
        echo Please set ANDROID_HOME environment variable
        pause
        exit /b 1
    )
)

SET EMULATOR_PATH=%ANDROID_HOME%\emulator\emulator.exe

REM Check if emulator exists
if not exist "%EMULATOR_PATH%" (
    echo ERROR: Emulator not found at %EMULATOR_PATH%
    echo Please install Android SDK Emulator
    pause
    exit /b 1
)

echo Found emulator at: %EMULATOR_PATH%
echo.

REM Check if AVD exists
"%EMULATOR_PATH%" -list-avds 2>nul | findstr /C:"%AVD_NAME%" >nul
if errorlevel 1 (
    echo WARNING: AVD "%AVD_NAME%" not found!
    echo.
    echo Available AVDs:
    "%EMULATOR_PATH%" -list-avds
    echo.
    echo Please create an AVD named "%AVD_NAME%" or update AVD_NAME in this script.
    echo.
    echo To create AVD through Android Studio:
    echo   1. Open Android Studio
    echo   2. Tools -^> Device Manager
    echo   3. Create Device -^> Pixel 6 -^> Android 13 API 33 Google APIs
    echo   4. Name it: %AVD_NAME%
    echo.
    pause
    exit /b 1
)

echo Starting AVD: %AVD_NAME%
echo.
echo NOTE: This will open emulator in a new window.
echo       Wait for it to fully boot (~2-3 minutes)
echo       Then run: 03_mask_device.bat
echo.

start "Android Emulator" "%EMULATOR_PATH%" -avd %AVD_NAME% -gpu host -no-snapshot-load

echo Emulator starting...
echo Waiting for device to connect...
echo.

REM Wait for device
timeout /t 5 /nobreak >nul
adb wait-for-device

echo.
echo Device connected!
echo Waiting for boot to complete...

REM Wait for boot to complete
:wait_boot
adb shell "getprop sys.boot_completed" 2>nul | findstr "1" >nul
if errorlevel 1 (
    timeout /t 2 /nobreak >nul
    goto wait_boot
)

echo.
echo ========================================
echo  Emulator is ready!
echo.
echo  Next steps:
echo    1. Run: 03_mask_device.bat
echo    2. Then: 04_install_frida.bat
echo ========================================
echo.

pause
