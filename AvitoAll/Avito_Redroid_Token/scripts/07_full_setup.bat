@echo off
echo ========================================
echo   FULL AUTOMATIC SETUP
echo   Avito Token Extraction System
echo ========================================
echo.
echo This script will:
echo   1. Check Docker installation
echo   2. Start Redroid container
echo   3. Setup device as Pixel 6
echo   4. Install Frida Server
echo   5. Install Avito APK
echo   6. Wait for manual authorization
echo   7. Extract tokens
echo.
echo Estimated time: 10-15 minutes
echo.
pause

cd /d %~dp0

REM Step 1
echo.
echo ========================================
echo STEP 1/7: Checking Docker
echo ========================================
call 01_install_docker.bat
if %errorlevel% neq 0 (
    echo.
    echo [X] Docker check failed
    echo Please fix Docker installation first
    pause
    exit /b 1
)

REM Step 2
echo.
echo ========================================
echo STEP 2/7: Starting Redroid
echo ========================================
call 02_start_redroid.bat
if %errorlevel% neq 0 (
    echo.
    echo [X] Failed to start Redroid
    pause
    exit /b 1
)

REM Step 3
echo.
echo ========================================
echo STEP 3/7: Setting up device masking
echo ========================================
call 03_setup_device.bat
if %errorlevel% neq 0 (
    echo.
    echo [X] Failed to setup device
    pause
    exit /b 1
)

REM Step 4
echo.
echo ========================================
echo STEP 4/7: Installing Frida Server
echo ========================================
call 04_install_frida.bat
if %errorlevel% neq 0 (
    echo.
    echo [X] Failed to install Frida
    pause
    exit /b 1
)

REM Step 5
echo.
echo ========================================
echo STEP 5/7: Installing Avito APK
echo ========================================
call 05_install_avito.bat
if %errorlevel% neq 0 (
    echo.
    echo [X] Failed to install Avito
    pause
    exit /b 1
)

REM Step 6 - Manual authorization
echo.
echo ========================================
echo STEP 6/7: MANUAL AUTHORIZATION REQUIRED
echo ========================================
echo.
echo Now you need to:
echo   1. View device screen (see options below)
echo   2. Open Avito app
echo   3. Login with phone + SMS code
echo   4. Open 'Messages' tab
echo   5. Wait 30 seconds
echo.
echo === Viewing Device Screen ===
echo.
echo OPTION A - scrcpy (recommended):
echo   winget install scrcpy
echo   scrcpy -s 127.0.0.1:5555
echo.
echo OPTION B - VNC Viewer:
echo   Connect to: 127.0.0.1:5900
echo   Download: https://www.realvnc.com/en/connect/download/viewer/
echo.
echo OPTION C - ADB screenshots (basic):
echo   docker exec avito-redroid screencap -p /sdcard/screen.png
echo   docker cp avito-redroid:/sdcard/screen.png screen.png
echo   (open screen.png)
echo.

REM Launch Avito
echo Starting Avito app...
docker exec avito-redroid am start -n com.avito.android/.Launcher

echo.
echo ========================================
echo  Waiting for your authorization...
echo ========================================
echo.
echo When you finish authorization, press any key to continue
pause

REM Step 7
echo.
echo ========================================
echo STEP 7/7: Extracting tokens
echo ========================================
call 06_extract_tokens.bat
if %errorlevel% neq 0 (
    echo.
    echo [X] Failed to extract tokens
    echo.
    echo Possible reasons:
    echo   - Not logged in to Avito
    echo   - Didn't open Messages tab
    echo   - Need to wait longer after login
    echo.
    echo Try running 06_extract_tokens.bat again after 1-2 minutes
    pause
    exit /b 1
)

echo.
echo ========================================
echo   SETUP COMPLETE!
echo ========================================
echo.
echo Your tokens are saved in: ..\output\
echo.
echo What's next?
echo   - Use tokens for Avito API (see README.md)
echo   - Setup automatic refresh (see examples)
echo   - Deploy to production server (see Avito_Token_SRV.md)
echo.
echo To extract tokens again:
echo   scripts\06_extract_tokens.bat
echo.
echo To stop Redroid:
echo   docker-compose stop
echo.
echo To start Redroid:
echo   scripts\02_start_redroid.bat
echo.
pause
