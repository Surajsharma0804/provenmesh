@echo off
title ProvenMesh
color 0A
echo.
echo  ProvenMesh - AI Ecosystem Intelligence Pipeline
echo  =================================================
echo.

:: ── Step 1: Start Docker infrastructure ──────────────────────────────────────
echo [1/3] Starting Docker (Postgres + Redis + MinIO)...
docker compose up -d postgres redis minio minio-init
if %errorlevel% neq 0 (
    echo.
    echo  ERROR: Docker failed to start.
    echo  Make sure Docker Desktop is running, then try again.
    echo.
    pause
    exit /b 1
)
echo  OK - Infrastructure running
echo.

:: ── Step 2: Wait for services ────────────────────────────────────────────────
echo [2/3] Waiting for services to be ready...
timeout /t 6 /nobreak > nul
echo  OK - Services ready
echo.

:: ── Step 3: Launch pipeline in background ────────────────────────────────────
echo [3/3] Starting ProvenMesh pipeline in background...
echo.
echo  Dashboard : https://docs.google.com/spreadsheets/d/130p3Bo5gZRBHWt9tK8J8BqVP5YY2ckaoCWW1UeC7vEc
echo  Log file  : logs\pipeline.log
echo  Export    : Every 20 minutes
echo.

:: Create logs directory
if not exist logs mkdir logs

:: Start pipeline as a detached background process
:: You can close this window — the pipeline keeps running
start /B "ProvenMesh" .venv\Scripts\python.exe -m provenmesh.main run ^
  --crawl-workers 3 ^
  --extract-workers 2 ^
  --resolve-workers 2 ^
  --auto-export ^
  --export-interval 20 ^
  > logs\pipeline.log 2>&1

echo  Pipeline started! PID logged to logs\pipeline.log
echo.
echo  You can now CLOSE this window — the pipeline keeps running.
echo  To stop it: run stop.bat  OR  open Task Manager and end python.exe
echo.
pause
