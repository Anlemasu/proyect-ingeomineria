@echo off
REM Cierre de caja automatico - ejecutado por Windows Task Scheduler a las 00:00
REM Registra la salida en auto_close_cash.log junto a este archivo

set PROJECT_ROOT=C:\Proyectos\proyect-ingeomineria
set PYTHON=%PROJECT_ROOT%\venv\Scripts\python.exe
set MANAGE=%PROJECT_ROOT%\sigmo_backend\manage.py
set LOG=%PROJECT_ROOT%\sigmo_backend\auto_close_cash.log

echo [%DATE% %TIME%] Iniciando cierre automatico... >> "%LOG%"
"%PYTHON%" "%MANAGE%" auto_close_cash >> "%LOG%" 2>&1
set EXITCODE=%ERRORLEVEL%
echo [%DATE% %TIME%] Proceso finalizado con codigo %EXITCODE%. >> "%LOG%"
REM Sin esto, el ultimo comando ejecutado era el echo de arriba (siempre
REM exitoso) y Task Scheduler reportaba LastTaskResult=0 aunque el cierre
REM realmente hubiera fallado -- asi paso inadvertido el fallo del
REM 2026-09-12 (Decimal no serializable) hasta revisar el .log a mano.
exit /b %EXITCODE%
