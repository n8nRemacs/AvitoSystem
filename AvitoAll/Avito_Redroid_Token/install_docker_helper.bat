@echo off
echo ========================================
echo   Docker Desktop Installation Helper
echo ========================================
echo.
echo Docker is NOT installed on this system.
echo.
echo To install Docker Desktop:
echo.
echo 1. Opening Docker Desktop download page in browser...
start https://www.docker.com/products/docker-desktop/
echo.
echo 2. Download "Docker Desktop for Windows"
echo.
echo 3. Run the installer (Docker Desktop Installer.exe)
echo.
echo 4. During installation:
echo    - Check "Use WSL 2 instead of Hyper-V" (recommended)
echo    - Accept default settings
echo.
echo 5. After installation:
echo    - Restart your computer
echo    - Launch Docker Desktop from Start Menu
echo    - Wait for green whale icon in system tray
echo.
echo 6. Then run this script again to continue setup:
echo    scripts\07_full_setup.bat
echo.
echo ========================================
echo   Alternative: Install via winget
echo ========================================
echo.
echo If you have winget (Windows 11), you can install Docker with:
echo.
echo   winget install Docker.DockerDesktop
echo.
choice /C YN /M "Try installing via winget now"
if errorlevel 2 goto :manual
if errorlevel 1 goto :winget_install

:winget_install
echo.
echo Installing Docker Desktop via winget...
winget install Docker.DockerDesktop

if %errorlevel% equ 0 (
    echo.
    echo [OK] Docker Desktop installed!
    echo.
    echo IMPORTANT: You MUST restart your computer now
    echo After restart, launch Docker Desktop and wait for it to start
    echo Then run: scripts\07_full_setup.bat
    echo.
    choice /C YN /M "Restart computer now"
    if errorlevel 1 shutdown /r /t 30 /c "Restarting to complete Docker Desktop installation..."
) else (
    echo.
    echo [X] winget installation failed
    echo Please install manually from: https://www.docker.com/products/docker-desktop/
)

goto :end

:manual
echo.
echo Please install Docker Desktop manually from the browser
echo After installation and restart, run: scripts\07_full_setup.bat
echo.

:end
pause
