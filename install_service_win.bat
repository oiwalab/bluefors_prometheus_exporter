@echo off
REM Windows Service Installation Script for Bluefors Prometheus Exporter
REM This script installs the Bluefors Prometheus Exporter as a Windows service

setlocal EnableDelayedExpansion

echo === Bluefors Monitor Service Installation (Windows) ===
echo.

REM Check if running as Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: This script must be run as Administrator
    echo Right-click on this file and select "Run as administrator"
    pause
    exit /b 1
)

REM Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM Check if Python is available via uv
uv run python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: Python is not available via uv
    echo Please ensure uv is properly installed with Python 3.12 or later
    pause
    exit /b 1
)

REM Check if uv is installed
uv --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: uv is not installed or not in PATH
    echo Please install uv: pip install uv
    pause
    exit /b 1
)

REM Check if required files exist
if not exist "bluefors_prometheus_exporter.py" (
    echo Error: bluefors_prometheus_exporter.py not found
    pause
    exit /b 1
)

if not exist "bluefors_service_win.py" (
    echo Error: bluefors_service_win.py not found
    pause
    exit /b 1
)

if not exist "config.yaml" (
    echo Error: config.yaml not found
    echo Please create a config.yaml file based on config.yaml.example
    pause
    exit /b 1
)

echo Installing dependencies...
uv sync

echo.
echo Installing Windows service...
uv run python bluefors_service_win.py install

if %errorLevel% equ 0 (
    echo.
    echo Service installed successfully!
    echo.
    echo Starting service...
    uv run python bluefors_service_win.py start
    
    if %errorLevel% equ 0 (
        echo Service started successfully!
        echo.
        echo Service Management Commands:
        echo   Status:  uv run python bluefors_service_win.py status
        echo   Start:   uv run python bluefors_service_win.py start
        echo   Stop:    uv run python bluefors_service_win.py stop
        echo   Restart: uv run python bluefors_service_win.py restart
        echo   Remove:  uv run python bluefors_service_win.py remove
        echo.
        echo The service will automatically start when Windows boots.
        echo Metrics are available at: http://{ip_address}:{port}/metrics
        echo.
        echo Check the log file at: %SCRIPT_DIR%bluefors_exporter.log
    ) else (
        echo Failed to start service!
        echo Check the Windows Event Viewer for details
    )
) else (
    echo Failed to install service!
    echo Make sure you have the necessary permissions
)

pause