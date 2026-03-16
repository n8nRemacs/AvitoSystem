@echo off
REM ========================================
REM  Auto-Refresh Avito Tokens
REM ========================================
REM
REM This script monitors token expiration and
REM automatically refreshes them using refresh_token
REM
REM IMPORTANT: Requires Avito token_manager script
REM ========================================

echo.
echo ========================================
echo  Avito Token Auto-Refresh
echo ========================================
echo.

REM Configuration
SET CHECK_INTERVAL=3600
SET REFRESH_THRESHOLD=7200
SET LOG_DIR=..\logs
SET OUTPUT_DIR=..\output

REM Create directories if they don't exist
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
if not exist "%OUTPUT_DIR%" mkdir "%OUTPUT_DIR%"

REM Generate log filename with date
for /f "tokens=1-3 delims=/ " %%a in ('date /t') do (set LOGDATE=%%c%%b%%a)
SET LOG_FILE=%LOG_DIR%\token_manager_%LOGDATE%.log

echo Configuration:
echo   Check interval:      %CHECK_INTERVAL% seconds (1 hour)
echo   Refresh threshold:   %REFRESH_THRESHOLD% seconds (2 hours before expiry)
echo   Log file:            %LOG_FILE%
echo   Output directory:    %OUTPUT_DIR%
echo.

REM Check if token_manager exists
if not exist "..\..\avito_token_manager.py" (
    echo ERROR: avito_token_manager.py not found!
    echo.
    echo Expected location: APK\Avito\avito_token_manager.py
    echo.
    echo This script is required for auto-refresh functionality.
    pause
    exit /b 1
)

echo Starting Token Manager in daemon mode...
echo.
echo IMPORTANT:
echo   - This will run continuously
echo   - Press Ctrl+C to stop
echo   - Logs will be saved to: %LOG_FILE%
echo.
echo Starting in 5 seconds...
timeout /t 5

echo.
echo ========================================
echo  Token Manager Running
echo ========================================
echo.

REM Run token manager with logging
python ..\..\avito_token_manager.py ^
    --daemon ^
    --check-interval %CHECK_INTERVAL% ^
    --refresh-threshold %REFRESH_THRESHOLD% ^
    --output-dir "%OUTPUT_DIR%" ^
    --log-file "%LOG_FILE%"

echo.
echo ========================================
echo  Token Manager stopped
echo.
echo  Check logs: %LOG_FILE%
echo ========================================
echo.

pause
