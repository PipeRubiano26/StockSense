@echo off
REM Construye la imagen y despliega StockSense en Kubernetes (minikube).
REM Requisito: Docker Desktop abierto (icono de la ballena quieto).
setlocal
set VERSION=1.0.2
cd /d "%~dp0\.."

echo [1/5] Verificando minikube...
minikube status >nul 2>&1
if errorlevel 1 (
  echo       Iniciando minikube (la primera vez tarda unos minutos^)...
  minikube start --driver=docker --memory=2600 --cpus=2 || goto :error
)

echo [2/5] Construyendo la imagen stocksense:%VERSION% ...
docker build -t stocksense:%VERSION% . || goto :error

echo [3/5] Cargando la imagen en minikube...
minikube image load stocksense:%VERSION% || goto :error

echo [4/5] Aplicando los manifiestos de k8s\ ...
kubectl apply -k k8s || goto :error

echo [5/5] Esperando a que las 2 replicas esten listas...
kubectl -n stocksense rollout status deploy/stocksense --timeout=300s || goto :error
kubectl -n stocksense get pods -o wide
echo.
echo Listo. Ejecute k8s\abrir_app.bat para abrir la aplicacion.
pause
exit /b 0

:error
echo.
echo ERROR: revise que Docker Desktop este abierto y vuelva a intentarlo.
pause
exit /b 1
