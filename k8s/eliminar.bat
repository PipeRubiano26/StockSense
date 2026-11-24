@echo off
REM Elimina StockSense del cluster. Los datos quedan en el nodo (/data/stocksense) salvo que se borre el volumen.
kubectl delete -k "%~dp0."
pause
