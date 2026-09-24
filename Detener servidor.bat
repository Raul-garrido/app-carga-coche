@echo off
setlocal enabledelayedexpansion
echo Buscando el servidor en el puerto 8000...

set FOUND=0
for /f "tokens=5" %%p in ('netstat -aon ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo Deteniendo proceso %%p...
    taskkill /PID %%p /F >nul 2>&1
    set FOUND=1
)

if "%FOUND%"=="1" (
    echo Servidor detenido.
) else (
    echo No habia ningun servidor escuchando en el puerto 8000.
)

timeout /t 3
