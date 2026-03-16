@echo off
REM ========================================
REM  Install Avito APK on Emulator
REM ========================================

echo.
echo ========================================
echo  Installing Avito
echo ========================================
echo.

REM Configuration
SET AVITO_APK=..\..\avito.apk

REM Check if APK exists
if not exist "%AVITO_APK%" (
    echo ERROR: Avito APK not found!
    echo.
    echo Expected location: %AVITO_APK%
    echo.
    echo Please place Avito APK at:
    echo   APK\Avito\avito.apk
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

echo Installing Avito...
echo.

adb install -r "%AVITO_APK%"
if errorlevel 1 (
    echo.
    echo WARNING: Installation may have failed
    echo.
    echo Common reasons:
    echo   1. APK architecture mismatch (ARM vs x86)
    echo   2. Corrupted APK file
    echo   3. Insufficient storage on emulator
    echo.
    echo Try:
    echo   - Use x86 version of Avito APK
    echo   - Increase emulator storage
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  Avito installed successfully!
echo.
echo  NEXT STEPS:
echo.
echo  1. Open Avito on emulator
echo  2. Login with phone number
echo  3. Enter SMS code
echo  4. Go to "Messages" tab
echo  5. Run: 06_extract_tokens.bat
echo.
echo ========================================
echo.

pause
