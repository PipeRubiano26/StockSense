@echo off
REM Demo de autorrecuperacion: provoca una falla real en una replica de StockSense.
REM Abra ver_pods.bat en otra ventana para ver como Kubernetes la recupera.
setlocal
:menu
echo.
echo  ===== StockSense - demo de autorrecuperacion =====
kubectl -n stocksense get pods
echo.
echo  1. Eliminar un pod          (el Deployment crea uno nuevo)
echo  2. Tumbar el proceso        (el contenedor se reinicia: RESTARTS +1)
echo  3. Colgar la aplicacion     (liveness falla y Kubernetes la reinicia)
echo  4. Ver eventos recientes
echo  5. Salir
set /p OPCION=Elija una opcion: 
for /f "delims=" %%P in ('kubectl -n stocksense get pods -l app^=stocksense -o jsonpath^="{.items[0].metadata.name}"') do set POD=%%P
if "%OPCION%"=="1" kubectl -n stocksense delete pod %POD% --wait=false
if "%OPCION%"=="2" kubectl -n stocksense exec %POD% -c stocksense -- python -c "import urllib.request as u;print(u.urlopen(u.Request('http://localhost:5000/health/chaos/crash',method='POST')).read().decode())"
if "%OPCION%"=="3" kubectl -n stocksense exec %POD% -c stocksense -- python -c "import urllib.request as u;print(u.urlopen(u.Request('http://localhost:5000/health/chaos/hang',method='POST')).read().decode())"
if "%OPCION%"=="4" kubectl -n stocksense get events --sort-by=.lastTimestamp
if "%OPCION%"=="5" exit /b 0
goto :menu
