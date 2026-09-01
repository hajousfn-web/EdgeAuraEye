@echo off
SETLOCAL ENABLEEXTENSIONS
cd /d "%~dp0"

set "ROOT=%~dp0"
set "VENV_DIR="

if exist "%ROOT%venv\Scripts\activate.bat" set "VENV_DIR=%ROOT%venv"
if exist "%ROOT%.venv\Scripts\activate.bat" set "VENV_DIR=%ROOT%.venv"

if not "%VENV_DIR%"=="" (
    echo Activating environment: %VENV_DIR%
    call "%VENV_DIR%\Scripts\activate.bat"
) else (
    echo No venv detected. Falling back to the system Python runtime.
)

where python >nul 2>nul
if errorlevel 1 (
    where py >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python is not installed or not available on PATH.
        exit /b 1
    )
    set "PYTHON_CMD=py"
) else (
    set "PYTHON_CMD=python"
)

for %%D in (flask cv2 numpy) do (
    %PYTHON_CMD% -c "import %%D" >nul 2>nul
    if errorlevel 1 (
        echo Installing missing dependency: %%D
        %PYTHON_CMD% -m pip install flask opencv-python numpy
    )
)

start "Ego Dashboard" http://127.0.0.1:5000
start "Ego Flask Server" cmd /k "%PYTHON_CMD% app.py"

echo ==================================================
echo Ego dashboard is launching in the background.
echo Open: http://127.0.0.1:5000

echo ==================================================
exit /b 0
