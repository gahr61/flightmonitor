@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo No se encontro el entorno virtual .venv
    echo Ejecuta primero: python -m venv .venv
    echo Y luego: .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

.venv\Scripts\python.exe -m app.main

echo.
echo El monitor se detuvo.
pause
