@echo off
REM Demo without hardware (Windows): gateway replays one day for 5 workers + dashboard
REM Usage: run_virtual_demo.bat [day] [start] [speed]      e.g. run_virtual_demo.bat 2026-10-05 09:50 20
set DAY=%1
if "%DAY%"=="" set DAY=2026-10-05
set START=%2
if "%START%"=="" set START=09:50
set SPEED=%3
if "%SPEED%"=="" set SPEED=20
cd /d "%~dp0\.."
if exist logs rmdir /s /q logs
set ARGS=
for %%i in (1 2 3 4 5) do if exist data\week\raw_1hz\W0%%i_%DAY%.csv.gz call set ARGS=%%ARGS%% --replay data\week\raw_1hz\W0%%i_%DAY%.csv.gz
start "PestGuard gateway" cmd /k python gateway\pestguard_gateway.py %ARGS% --speed %SPEED% --start %START%
timeout /t 3 >nul
streamlit run dashboard\dashboard.py
