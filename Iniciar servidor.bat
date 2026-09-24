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

echo.
echo Arrancando el servidor en una ventana aparte...
start "Calculadora de carga - servidor" ".venv\Scripts\python.exe" -m uvicorn app.main:app --port 8000

timeout /t 3 /nobreak >nul
start "" http://localhost:8000

echo.
echo Listo. El servidor sigue en marcha en la ventana "Calculadora de carga - servidor".
echo No la cierres mientras uses la app. Para pararlo, usa "Detener servidor.bat"
echo (o cierra esa ventana directamente).
echo Esta ventana se puede cerrar sin problema.
timeout /t 5
