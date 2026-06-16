@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM Make sure Windows built-in commands (timeout, netstat, taskkill, ...) are findable
REM even when user's PATH is broken/truncated.
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%PATH%"

REM ============================================================
REM  MY-RAG one-click start
REM    1) check Docker Desktop
REM    2) check Ollama
REM    3) start redis + mysql containers
REM    4) start FastAPI in a new window
REM    5) start Gradio in a new window
REM ============================================================

cd /d "%~dp0"

echo.
echo ========================================
echo   MY-RAG starting...
echo ========================================
echo.

echo [1/5] Check Docker Desktop ...
docker info >nul 2>&1
if errorlevel 1 (
    echo   [ERROR] Docker is not running. Please start Docker Desktop first.
    pause
    exit /b 1
)
echo   OK

echo [2/5] Check Ollama service ...
curl -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo   [WARN] Ollama not running. Please open Ollama or run "ollama serve".
    echo          Script will continue, but Q^&A will be unavailable.
) else (
    echo   OK
)

echo [3/5] Start redis + mysql containers ...
docker compose up -d redis mysql
if errorlevel 1 (
    echo   [ERROR] docker compose failed.
    pause
    exit /b 1
)

echo   Waiting for MySQL to be ready ...
set /a tries=0
:wait_mysql
docker exec rag_mysql mysqladmin ping -uroot -ppassword --silent >nul 2>&1
if errorlevel 1 (
    set /a tries+=1
    if !tries! GEQ 30 (
        echo   [ERROR] MySQL ready timeout.
        pause
        exit /b 1
    )
    timeout /t 2 /nobreak >nul
    goto wait_mysql
)
echo   OK

echo [4/5] Start FastAPI in new window ...
start "MY-RAG API" cmd /k "chcp 65001 >nul && cd /d %~dp0 && venv\Scripts\python.exe -X utf8 scripts\start_api.py"

set /a tries=0
:wait_api
timeout /t 2 /nobreak >nul
curl -s --max-time 2 http://localhost:8000/ >nul 2>&1
if errorlevel 1 (
    set /a tries+=1
    if !tries! GEQ 15 (
        echo   [WARN] API ready timeout. Check the API window for errors.
        goto start_gradio
    )
    goto wait_api
)
echo   OK

:start_gradio
echo [5/5] Start Gradio in new window ...
start "MY-RAG Gradio" cmd /k "chcp 65001 >nul && cd /d %~dp0 && venv\Scripts\python.exe -X utf8 app\frontend\gradio_app.py"

echo.
echo ========================================
echo   All started!
echo ========================================
echo   API     : http://localhost:8000
echo   Web UI  : http://localhost:7860
echo   Redis   : localhost:6379  (container rag_redis)
echo   MySQL   : localhost:3307  (container rag_mysql)
echo ========================================
echo.
echo Tips:
echo   - Close the two new windows to stop API/Gradio
echo   - To stop everything (containers too), run stop.bat
echo.

pause
