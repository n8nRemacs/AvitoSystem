@echo off
REM ========================================
REM  Extract Avito Tokens from Emulator
REM ========================================

echo.
echo ========================================
echo  Extracting Avito Tokens
echo ========================================
echo.

REM Check ADB connection
adb devices | findstr /R "device$" >nul
if errorlevel 1 (
    echo ERROR: No Android device connected!
    echo Please start emulator: 02_start_emulator.bat
    pause
    exit /b 1
)

REM Check if Avito is installed
adb shell "pm list packages | grep com.avito.android" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Avito not installed!
    echo Please run: 05_install_avito.bat
    pause
    exit /b 1
)

echo [1/3] Getting root access...
adb root
timeout /t 2 /nobreak >nul
adb wait-for-device

echo.
echo [2/3] Reading SharedPreferences...
echo.

REM Read SharedPreferences file
adb shell "cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml" > temp_prefs.xml 2>nul

if not exist temp_prefs.xml (
    echo ERROR: Cannot read SharedPreferences!
    echo.
    echo Possible reasons:
    echo   1. Avito not logged in
    echo   2. No root access
    echo   3. File path changed
    echo.
    echo Please:
    echo   1. Make sure you logged in to Avito
    echo   2. Open Avito and wait 30 seconds
    echo   3. Run this script again
    echo.
    del temp_prefs.xml 2>nul
    pause
    exit /b 1
)

REM Check if file is not empty
for %%A in (temp_prefs.xml) do set SIZE=%%~zA
if %SIZE% LSS 100 (
    echo ERROR: SharedPreferences file is too small (%SIZE% bytes)
    echo.
    echo This usually means:
    echo   - Avito is not logged in
    echo   - Session data not saved yet
    echo.
    echo Please:
    echo   1. Open Avito on emulator
    echo   2. Login if needed
    echo   3. Open "Messages" tab
    echo   4. Wait 30 seconds
    echo   5. Run this script again
    echo.
    del temp_prefs.xml
    pause
    exit /b 1
)

echo Successfully read SharedPreferences (%SIZE% bytes)

echo.
echo [3/3] Parsing and saving tokens...
echo.

REM Generate timestamp for filename
for /f "tokens=1-4 delims=/ " %%a in ('date /t') do (set MYDATE=%%c%%b%%a)
for /f "tokens=1-2 delims=: " %%a in ('time /t') do (set MYTIME=%%a%%b)
SET TIMESTAMP=%MYDATE%_%MYTIME%

SET OUTPUT_FILE=..\output\session_%TIMESTAMP%.json

REM Call Python parser
python ..\..\avito_adb_sync.py --xml temp_prefs.xml --output "%OUTPUT_FILE%"

if errorlevel 1 (
    echo ERROR: Failed to parse tokens
    echo.
    echo The SharedPreferences file may not contain valid session data.
    echo.
    del temp_prefs.xml
    pause
    exit /b 1
)

REM Clean up
del temp_prefs.xml

echo.
echo ========================================
echo  Tokens extracted successfully!
echo.
echo  Output file: %OUTPUT_FILE%
echo.
echo  Contents:
echo    - session_token (JWT)
echo    - refresh_token
echo    - fingerprint (fpx)
echo    - device_id
echo    - user_id
echo    - expires_at
echo.
echo  You can use these tokens for Avito API requests.
echo.
echo  Next step (optional):
echo    07_auto_refresh.bat - Auto-refresh tokens
echo ========================================
echo.

REM Show file contents
if exist "%OUTPUT_FILE%" (
    echo Preview:
    type "%OUTPUT_FILE%" | more
)

echo.
pause
