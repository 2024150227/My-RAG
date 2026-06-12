@echo off
chcp 65001 >nul
setlocal

REM Make sure Windows built-in commands (netstat, taskkill, chcp, ...) are findable
REM even when user's PATH is broken/truncated.
set "PATH=%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem;%PATH%"

REM ============================================================
REM  MY-RAG one-click stop
REM    1) kill process on port 8000 (FastAPI)
REM    2) kill process on port 7860 (Gradio)
REM    3) stop redis + mysql containers
REM ============================================================

cd /d "%~dp0"

echo.
echo ========================================
echo   MY-RAG stopping...
echo ========================================
echo.

echo [1/3] Stop FastAPI on port 8000 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   OK

echo [2/3] Stop Gradio on port 7860 ...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":7860 " ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
)
echo   OK

echo [3/3] Stop redis + mysql containers ...
docker compose stop redis mysql >nul 2>&1
echo   OK

echo.
echo ========================================
echo   All stopped.
echo ========================================
echo.
echo Tips:
echo   - Containers are stopped but NOT removed (data preserved)
echo   - Next "start.bat" will reuse them
echo   - To fully clean (containers + network): docker compose down
echo.

pause
