@echo off
echo ============================================================
echo   Starting Avito with Device Masking (Google Pixel 6)
echo ============================================================

echo.
echo [1/3] Stopping Avito...
C:\Users\Dimon\AppData\Local\Android\Sdk\platform-tools\adb.exe shell "am force-stop com.avito.android"
timeout /t 2 > nul

echo [2/3] Starting Frida with spawn...
echo.
echo This will:
echo   - Launch Avito through Frida
echo   - Hook Build properties BEFORE Avito checks device
echo   - Device will appear as Google Pixel 6
echo.
echo IMPORTANT: Keep this window open!
echo.
pause

cd /d C:\Users\Dimon\Pojects\Reverce\APK\Avito

echo [3/3] Spawning Avito with masking...
C:\Users\Dimon\AppData\Local\Programs\Python\Python39-32\python.exe -m frida_tools.cli -H 127.0.0.1:27042 -f com.avito.android -l Studio_Token\frida_scripts\build_mask.js

pause
