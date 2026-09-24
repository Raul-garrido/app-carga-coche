@echo off
setlocal
cd /d "%~dp0backend"

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual de Python por primera vez...
    python -m venv .venv
)

".venv\Scripts\python.exe" -c "import fastapi" 2>nul
if errorlevel 1 (
    echo Instalando dependencias por primera vez, un momento...
    ".venv\Scripts\python.exe" -m pip install -q -r requirements-dev.txt
)

if exist requirements-myaudi.txt (
    ".venv\Scripts\python.exe" -c "import carconnectivity" 2>nul
    if errorlevel 1 (
        echo Instalando dependencias de MyAudi por primera vez, un momento...
        ".venv\Scripts\python.exe" -m pip install -q -r requirements-myaudi.txt
    )
)

set LANIP=
for /f "delims=" %%i in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.PrefixOrigin -ne 'WellKnown' } | Select-Object -First 1 -ExpandProperty IPAddress)" 2^>nul') do set LANIP=%%i

echo.
echo Arrancando el servidor en una ventana aparte...
start "Calculadora de carga - servidor" ".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000

timeout /t 3 /nobreak >nul

echo.
echo Listo. El servidor sigue en marcha en la ventana "Calculadora de carga - servidor".
echo No la cierres mientras uses la app. Para pararlo, usa "Detener servidor.bat"
echo (o cierra esa ventana directamente).
echo.
if not "%LANIP%"=="" (
    echo Desde el movil, en la MISMA wifi que este PC, abre:
    echo     http://%LANIP%:8000
    echo.
    echo La primera vez, es posible que Windows te pregunte si permites el
    echo acceso a Python/uvicorn en redes privadas: dale a "Permitir acceso".
) else (
    echo No se ha podido detectar la IP de este PC en la red. Ejecuta "ipconfig"
    echo y usa la IPv4 de tu Wi-Fi, con el movil en la MISMA wifi: http://TU_IP:8000
)
echo.
echo Esta ventana se puede cerrar sin problema.
timeout /t 8
