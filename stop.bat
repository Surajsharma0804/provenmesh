@echo off
title ProvenMesh - Stop
echo.
echo  Stopping ProvenMesh pipeline...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq ProvenMesh*" > nul 2>&1
taskkill /F /IM python.exe > nul 2>&1
echo  OK - Pipeline stopped
echo.
echo  Stopping Docker services...
docker compose stop
echo  OK - Docker stopped (data is saved)
echo.
pause
