@echo off
echo ========================================
echo   Extracting Avito Tokens
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

REM Check if Avito is installed
docker exec avito-redroid pm list packages | findstr com.avito.android >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Avito is not installed
    echo.
    echo Please run 05_install_avito.bat first
    echo.
    pause
    exit /b 1
)

echo [1/4] Checking Avito authorization...
docker exec avito-redroid ps | findstr com.avito.android >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Warning: Avito is not running
    echo.
    choice /C YN /M "Start Avito now"
    if errorlevel 1 docker exec avito-redroid am start -n com.avito.android/.Launcher
)

echo [OK] Ready

echo.
echo [2/4] Reading SharedPreferences...

REM Pull SharedPreferences XML
docker exec avito-redroid cat /data/data/com.avito.android/shared_prefs/com.avito.android_preferences.xml > temp_prefs.xml 2>nul

if not exist temp_prefs.xml (
    echo [X] Cannot read SharedPreferences
    echo.
    echo Make sure:
    echo   1. You are authorized in Avito
    echo   2. You opened 'Messages' tab
    echo   3. Wait 30 seconds after login
    echo.
    pause
    del temp_prefs.xml 2>nul
    exit /b 1
)

REM Check if file has content
for %%A in (temp_prefs.xml) do set FILE_SIZE=%%~zA
if %FILE_SIZE% LSS 100 (
    echo [X] SharedPreferences is empty
    echo.
    echo Please:
    echo   1. Open Avito app
    echo   2. Login with phone + SMS
    echo   3. Open 'Messages' tab
    echo   4. Wait 30 seconds
    echo   5. Run this script again
    echo.
    pause
    del temp_prefs.xml 2>nul
    exit /b 1
)

echo [OK] Found %FILE_SIZE% bytes

echo.
echo [3/4] Parsing tokens...

REM Use Python to parse XML and extract tokens
C:\Users\Dimon\AppData\Local\Programs\Python\Python39-32\python.exe automation\extract_tokens.py temp_prefs.xml

if %errorlevel% neq 0 (
    echo [X] Failed to parse tokens
    echo.
    echo Check temp_prefs.xml manually
    echo.
    pause
    del temp_prefs.xml 2>nul
    exit /b 1
)

del temp_prefs.xml

echo.
echo [4/4] Getting device info...
docker exec avito-redroid sh -c "echo 'Model: '$(getprop ro.product.model)"
docker exec avito-redroid sh -c "echo 'Manufacturer: '$(getprop ro.product.manufacturer)"
docker exec avito-redroid sh -c "echo 'Android: '$(getprop ro.build.version.release)"

echo.
echo ========================================
echo   Tokens extracted successfully!
echo ========================================
echo.
echo Output saved to: output\session_*.json
echo.
echo Token contains:
echo   - session_token (JWT)
echo   - refresh_token
echo   - fingerprint
echo   - device_id
echo   - user_id
echo   - expires_at
echo.
echo Use these tokens for Avito API requests
echo See README.md for usage examples
echo.
pause
