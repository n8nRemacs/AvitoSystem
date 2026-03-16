@echo off
REM ========================================
REM  Install Frida Server on Android Emulator
REM ========================================

echo.
echo ========================================
echo  Installing Frida Server
echo ========================================
echo.

REM Configuration
SET FRIDA_VERSION=17.6.2
SET FRIDA_FILE=frida-server-%FRIDA_VERSION%-android-x86_64
SET FRIDA_PATH=..\..\x86_test\%FRIDA_FILE%

REM Check if Frida file exists
if not exist "%FRIDA_PATH%" (
    echo ERROR: Frida Server not found!
    echo.
    echo Expected location: %FRIDA_PATH%
    echo.
    echo Download from:
    echo   https://github.com/frida/frida/releases/download/%FRIDA_VERSION%/%FRIDA_FILE%.xz
    echo.
    echo After download:
    echo   1. Extract .xz file (use 7-Zip)
    echo   2. Place in: APK\Avito\x86_test\
    echo   3. Run this script again
    echo.
    pause
    exit /b 1
)

REM Check ADB connection
adb devices | findstr /R "device$" >nul
if errorlevel 1 (
    echo ERROR: No Android device connected!
    echo Please start emulator: 02_start_emulator.bat
    pause
    exit /b 1
)

echo [1/4] Getting root access...
adb root
timeout /t 2 /nobreak >nul
adb wait-for-device

echo.
echo [2/4] Pushing Frida Server to device...
adb push "%FRIDA_PATH%" /data/local/tmp/frida-server
if errorlevel 1 (
    echo ERROR: Failed to push Frida Server
    pause
    exit /b 1
)

echo.
echo [3/4] Setting permissions...
adb shell "chmod 755 /data/local/tmp/frida-server"

echo.
echo [4/4] Starting Frida Server...
adb shell "pkill frida-server" >nul 2>&1
adb shell "/data/local/tmp/frida-server &" >nul 2>&1

timeout /t 3 /nobreak >nul

echo.
echo ========================================
echo  Verifying Frida Server...
echo ========================================
echo.

REM Test Frida
python -c "import frida; frida.get_usb_device()" >nul 2>&1
if errorlevel 1 (
    echo WARNING: Cannot connect to Frida!
    echo.
    echo Try manually:
    echo   frida-ps -U
    echo.
    echo If you see process list, Frida is working.
) else (
    echo SUCCESS: Frida Server is running!
    echo.
    echo Testing with frida-ps...
    echo.
    frida-ps -U | findstr /N "^" | more +1,10
    echo   ... (showing first 10 processes)
)

echo.
echo ========================================
echo  Frida Server installed successfully!
echo.
echo  Next step:
echo    05_install_avito.bat
echo ========================================
echo.

pause
