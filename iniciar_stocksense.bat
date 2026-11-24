@echo off
REM Inicia StockSense usando el Python del entorno virtual (no requiere activarlo)
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo No se encontro el entorno virtual .venv. Vea la seccion "Instalacion" del README.
  pause
  exit /b 1
)
echo Abriendo StockSense en http://127.0.0.1:5000  (Ctrl+C para detener)
start "" http://127.0.0.1:5000
".venv\Scripts\python.exe" app.py
pause
