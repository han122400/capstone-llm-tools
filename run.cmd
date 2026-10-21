@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0" || exit /b 1

set "PYTHON_EXE=python"
if exist ".venv\Scripts\python.exe" set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"

if /i "%~1"=="--backend" goto backend
if /i "%~1"=="--frontend" goto frontend

where node.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is required. Install Node.js 22.12 or newer.
    goto failed
)
where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm was not found in PATH.
    goto failed
)
if not exist "node_modules\vite\bin\vite.js" (
    echo [ERROR] Frontend dependencies are missing. Run: npm install
    goto failed
)
"%PYTHON_EXE%" -c "import sys; assert sys.version_info >= (3, 10); import fastapi, uvicorn, httpx" >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.10 or newer and backend dependencies are required.
    echo Create the environment: python -m venv .venv
    echo Install dependencies: .venv\Scripts\python.exe -m pip install -r backend\requirements.txt
    goto failed
)

call :check_port 8001
if errorlevel 2 goto port_error
if errorlevel 1 (
    echo [INFO] Port 8001 is already in use. Backend launch skipped.
) else (
    start "Sentinel - FastAPI" "%ComSpec%" /d /k call "%~f0" --backend
)

call :check_port 5174
if errorlevel 2 goto port_error
if errorlevel 1 (
    echo [INFO] Port 5174 is already in use. Frontend launch skipped.
) else (
    start "Sentinel - Vite" "%ComSpec%" /d /k call "%~f0" --frontend
)

echo.
echo Dashboard: http://127.0.0.1:5174
echo API docs:  http://127.0.0.1:8001/docs
echo Keep Ollama running. Stop each server with Ctrl+C in its window.
exit /b 0

:check_port
node -e "const net=require('node:net');const s=net.createServer();s.on('error',e=>process.exit(e.code==='EADDRINUSE'?1:2));s.listen(Number(process.argv[1]),'127.0.0.1',()=>s.close(()=>process.exit(0)));" %1 >nul 2>&1
exit /b %errorlevel%

:backend
title Sentinel - FastAPI
"%PYTHON_EXE%" -m uvicorn backend.main:app --reload --reload-dir backend --host 127.0.0.1 --port 8001
exit /b %errorlevel%

:frontend
title Sentinel - Vite
call npm.cmd run dev
exit /b %errorlevel%

:port_error
echo [ERROR] Could not check the local server ports.
goto failed

:failed
echo.
pause
exit /b 1
