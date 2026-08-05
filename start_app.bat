@echo off
setlocal

set "PROJECT_DIR=%~dp0"
cd /d "%PROJECT_DIR%"

echo ============================================
echo   Job Hunter Dashboard
echo ============================================
echo.

:: Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo [!] No .venv found. Creating virtual environment...
    python -m venv .venv
    call .venv\Scripts\activate.bat
)

:: Install dependencies only if requirements changed or never installed
set "MARKER=.deps_installed"
set "NEEDS_INSTALL=0"

if not exist "%MARKER%" (
    set "NEEDS_INSTALL=1"
) else (
    certutil -hashfile requirements.txt MD5 2>nul | findstr /v ":" > "%TEMP%\req_hash_new.txt"
    fc /b "%MARKER%" "%TEMP%\req_hash_new.txt" >nul 2>&1
    if errorlevel 1 set "NEEDS_INSTALL=1"
    del "%TEMP%\req_hash_new.txt" 2>nul
)

if "%NEEDS_INSTALL%"=="1" (
    echo [1/2] Installing dependencies from requirements.txt...
    pip install -r requirements.txt --quiet
    if errorlevel 1 (
        echo [!] pip install failed. Check requirements.txt.
        pause
        exit /b 1
    )
    certutil -hashfile requirements.txt MD5 2>nul | findstr /v ":" > "%MARKER%"
    echo      Done.
    echo.
) else (
    echo [ok] Dependencies already installed. Skipping pip install.
    echo.
)

echo [2/2] Launching Streamlit on http://localhost:8501
echo.
python -m streamlit run app.py

endlocal
