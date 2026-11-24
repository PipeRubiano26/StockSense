@echo off
REM Reinicia los datos de la base dentro del cluster (usar el dia de la Expo).
kubectl -n stocksense exec deploy/stocksense -c stocksense -- flask --app app init-db --reset
pause
