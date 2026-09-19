@echo off
title Cubix - Inteligencia Analitica y Cubos OLAP
echo ====================================================================
echo   Iniciando Cubix - Inteligencia Analitica y Cubos OLAP
echo ====================================================================
set PYTHONPATH=%CD%;%CD%\.venv\Lib\site-packages
echo Servidor escuchando en: http://localhost:8000
echo Usuarios disponibles: admin, analista, operador (clave = mismo nombre)
echo.
set PYTHON_BIN=.venv\Scripts\python.exe
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=%APPDATA%\uv\python\cpython-3.11.15-windows-x86_64-none\python.exe
)
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=%APPDATA%\uv\python\cpython-3.11-windows-x86_64-none\python.exe
)
if not exist "%PYTHON_BIN%" (
    set PYTHON_BIN=python
)

"%PYTHON_BIN%" -m uvicorn sistemaAnalitica.app.servidor:app --host 0.0.0.0 --port 8000 --reload
pause
