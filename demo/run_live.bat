@echo off
REM Real wearable(s): run_live.bat COM5 [COM7 ...]
cd /d "%~dp0\.."
set ARGS=
:loop
if "%1"=="" goto go
set ARGS=%ARGS% --port %1
shift
goto loop
:go
start "PestGuard gateway" cmd /k python gateway\pestguard_gateway.py %ARGS%
timeout /t 3 >nul
streamlit run dashboard\dashboard.py
