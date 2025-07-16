@echo off
REM Windows Service Uninstallation Script for Bluefors Prometheus Exporter

setlocal EnableDelayedExpansion

echo === Bluefors Monitor Service Uninstallation (Windows) ===
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

REM Check if uv is installed
uv --version >nul 2>&1
if %errorLevel% neq 0 (
    echo Error: uv is not installed or not in PATH
    pause
    exit /b 1
)

REM Check if service script exists
if not exist "bluefors_service_win.py" (
    echo Error: bluefors_service_win.py not found
    pause
    exit /b 1
)

echo Stopping service if running...
uv run python bluefors_service_win.py stop >nul 2>&1

echo Removing Windows service...
uv run python bluefors_service_win.py remove

if %errorLevel% equ 0 (
    echo.
    echo Service uninstalled successfully!
) else (
    echo.
    echo Failed to uninstall service!
    echo The service may not be installed or you may need Administrator privileges
)

pause