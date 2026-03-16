@echo off
REM ========================================
REM  Environment Check for Avito Token Manager
REM ========================================

echo.
echo ========================================
echo  Environment Check
echo ========================================
echo.

SET ALL_OK=1

REM Check Python
echo [1/5] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo   - ERROR: Python not found!
    echo   - Please install Python 3.8+ from https://www.python.org/
    SET ALL_OK=0
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo   - OK: Python %%i
)

REM Check Frida
echo.
echo [2/5] Checking Frida...
python -c "import frida; print('Frida', frida.__version__)" >nul 2>&1
if errorlevel 1 (
    echo   - ERROR: Frida not installed!
    echo   - Install: pip install frida-tools
    SET ALL_OK=0
) else (
    for /f "tokens=*" %%i in ('python -c "import frida; print('Frida', frida.__version__)"') do echo   - OK: %%i
)

REM Check ADB
echo.
echo [3/5] Checking ADB...
adb version >nul 2>&1
if errorlevel 1 (
    echo   - ERROR: ADB not found!
    echo   - Please install Android SDK and add platform-tools to PATH
    SET ALL_OK=0
) else (
    for /f "tokens=1,5" %%i in ('adb version ^| findstr /R "^Android"') do echo   - OK: ADB version %%j
)

REM Check Android SDK
echo.
echo [4/5] Checking Android SDK...
if not defined ANDROID_HOME (
    echo   - WARNING: ANDROID_HOME not set
    echo   - Trying to find Android SDK...

    if exist "%LOCALAPPDATA%\Android\Sdk" (
        SET ANDROID_HOME=%LOCALAPPDATA%\Android\Sdk
        echo   - OK: Found at %LOCALAPPDATA%\Android\Sdk
    ) else (
        echo   - ERROR: Android SDK not found!
        echo   - Please install Android Studio
        SET ALL_OK=0
    )
) else (
    echo   - OK: ANDROID_HOME=%ANDROID_HOME%
)

REM Check Emulator
echo.
echo [5/5] Checking Emulator...
if defined ANDROID_HOME (
    if exist "%ANDROID_HOME%\emulator\emulator.exe" (
        echo   - OK: Emulator found
    ) else (
        echo   - WARNING: Emulator not found at %ANDROID_HOME%\emulator\
        SET ALL_OK=0
    )
) else (
    echo   - SKIP: Cannot check without ANDROID_HOME
)

echo.
echo ========================================
if %ALL_OK%==1 (
    echo  Result: ALL CHECKS PASSED!
    echo.
    echo  You are ready to proceed with:
    echo    02_start_emulator.bat
) else (
    echo  Result: SOME CHECKS FAILED
    echo.
    echo  Please fix the errors above before proceeding.
)
echo ========================================
echo.

pause
