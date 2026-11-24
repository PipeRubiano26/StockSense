@echo off
REM Muestra los pods en tiempo real (Ctrl+C para salir). Util durante la demo de fallas.
kubectl -n stocksense get pods -o wide -w
