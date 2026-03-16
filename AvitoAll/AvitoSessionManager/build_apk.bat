@echo off
set JAVA_HOME=C:\Program Files\Android\Android Studio\jbr
set PATH=%JAVA_HOME%\bin;%PATH%
cd /d C:\Users\User\Documents\Revers\APK\Avito\AvitoSessionManager
call gradlew.bat assembleDebug
