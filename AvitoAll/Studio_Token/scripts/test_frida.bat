@echo off
echo Testing Frida connection...
cd %~dp0
C:\Users\Dimon\AppData\Local\Programs\Python\Python39-32\Scripts\frida-ps.exe -U > frida_test_output.txt 2>&1
echo Frida test complete. Output saved to frida_test_output.txt
type frida_test_output.txt
