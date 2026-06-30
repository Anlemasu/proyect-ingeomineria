@echo off
REM Cierre de caja automatico — ejecutado por Windows Task Scheduler a las 00:00
REM Registra la salida en auto_close_cash.log junto a este archivo

set PROJECT_ROOT=C:\Proyectos\proyect-ingeomineria
set PYTHON=%PROJECT_ROOT%\venv\Scripts\python.exe
set MANAGE=%PROJECT_ROOT%\sigmo_backend\manage.py
set LOG=%PROJECT_ROOT%\sigmo_backend\auto_close_cash.log

echo [%DATE% %TIME%] Iniciando cierre automatico... >> "%LOG%"
"%PYTHON%" "%MANAGE%" auto_close_cash >> "%LOG%" 2>&1
echo [%DATE% %TIME%] Proceso finalizado con codigo %ERRORLEVEL%. >> "%LOG%"
