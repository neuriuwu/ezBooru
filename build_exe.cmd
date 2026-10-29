@echo off
setlocal
set "PROJECT_ROOT=%~dp0"
set "PYTHON=%PROJECT_ROOT%.venv\Scripts\python.exe"

if not exist "%PYTHON%" (
    echo Project virtual environment not found. Create it with: python -m venv .venv
    exit /b 1
)

pushd "%PROJECT_ROOT%"
"%PYTHON%" -m pip install -e ".[build]"
if errorlevel 1 goto failed

"%PYTHON%" "%PROJECT_ROOT%tools\build_icon.py"
if errorlevel 1 goto failed

"%PYTHON%" -m PyInstaller --clean --noconfirm --onefile --windowed --name ezBooru --icon "%PROJECT_ROOT%assets\ezBooru.ico" --add-data "%PROJECT_ROOT%assets\ezBooru.ico;." --collect-all qasync "%PROJECT_ROOT%ezbooru\main.py"
if errorlevel 1 goto failed

echo Standalone executable created: %PROJECT_ROOT%dist\ezBooru.exe
popd
exit /b 0

:failed
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
popd
exit /b %BUILD_EXIT_CODE%
