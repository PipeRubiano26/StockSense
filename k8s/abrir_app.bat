@echo off
REM Abre StockSense (servido por Kubernetes) en el navegador.
REM Deje esta ventana abierta mientras use la aplicacion: es el tunel hacia el cluster.
minikube service stocksense -n stocksense
pause
