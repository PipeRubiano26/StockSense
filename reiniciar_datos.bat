@echo off
REM Borra la base de datos y vuelve a cargar los datos iniciales (usar el dia de la Expo)
cd /d "%~dp0"
".venv\Scripts\python.exe" -m flask --app app init-db --reset
pause
