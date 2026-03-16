@echo off
echo ========================================
echo   Installing Frida Server on Redroid
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

REM Check Frida version
echo [1/5] Checking Frida installation...
C:\Users\Dimon\AppData\Local\Programs\Python\Python39-32\Scripts\frida.exe --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Frida is not installed on host
    echo.
    echo Install Frida:
    echo   python -m pip install frida-tools
    echo.
    pause
    exit /b 1
)

for /f %%i in ('C:\Users\Dimon\AppData\Local\Programs\Python\Python39-32\Scripts\frida.exe --version') do set FRIDA_VERSION=%%i
echo [OK] Frida %FRIDA_VERSION% installed

echo.
echo [2/5] Downloading Frida Server for Android x86_64...

REM Download Frida Server
if not exist "frida-server" (
    curl -L -o frida-server.xz "https://github.com/frida/frida/releases/download/%FRIDA_VERSION%/frida-server-%FRIDA_VERSION%-android-x86_64.xz"

    if %errorlevel% neq 0 (
        echo [X] Failed to download Frida Server
        pause
        exit /b 1
    )

    echo Extracting...
    tar -xf frida-server.xz
    ren frida-server-%FRIDA_VERSION%-android-x86_64 frida-server
    del frida-server.xz
)

echo [OK] Downloaded

echo.
echo [3/5] Copying Frida Server to container...
docker cp frida-server avito-redroid:/data/local/tmp/frida-server
docker exec avito-redroid chmod 755 /data/local/tmp/frida-server

echo.
echo [4/5] Starting Frida Server...
REM Kill existing frida-server if running
docker exec avito-redroid pkill -9 frida-server 2>nul

REM Start frida-server in background
docker exec -d avito-redroid /data/local/tmp/frida-server

timeout /t 2 >nul

REM Check if running
docker exec avito-redroid ps | findstr frida-server >nul 2>&1
if %errorlevel% neq 0 (
    echo [X] Frida Server failed to start
    echo.
    echo Check logs:
    echo   docker exec avito-redroid logcat -s frida
    echo.
    pause
    exit /b 1
)

echo [OK] Frida Server is running

echo.
echo [5/5] Testing connection...
C:\Users\Dimon\AppData\Local\Programs\Python\Python39-32\Scripts\frida-ps.exe -R >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Warning: Cannot connect to Frida Server
    echo    This is normal if using remote connection
    echo.
)

echo.
echo ========================================
echo   Frida Server installed!
echo ========================================
echo.
echo Server: /data/local/tmp/frida-server
echo Port: 27042 (default)
echo.
echo Test connection:
echo   docker exec avito-redroid ps ^| findstr frida
echo.
echo Next step: Run 05_install_avito.bat
echo.
pause
