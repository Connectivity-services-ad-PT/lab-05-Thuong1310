@echo off
REM Multi-Machine Setup Script for IoT and Core Business
REM Usage: setup_machine.bat <role> <broker_ip>
REM Example:
REM   setup_machine.bat iot 192.168.1.50
REM   setup_machine.bat core 192.168.1.50

setlocal enabledelayedexpansion

if "%1"=="" (
    echo Usage: setup_machine.bat ^<role^> ^<broker_ip^>
    echo.
    echo Roles:
    echo   iot   - Run IoT Ingestion service
    echo   core  - Run Core Business service
    echo   demo  - Send demo events
    echo.
    echo Example:
    echo   setup_machine.bat iot 192.168.1.50
    echo   setup_machine.bat core 192.168.1.50
    echo   setup_machine.bat demo 192.168.1.50
    exit /b 1
)

set ROLE=%1
set BROKER_IP=%2

if "%BROKER_IP%"=="" (
    set BROKER_IP=localhost
)

echo.
echo ============================================
echo Smart Campus - Multi-Machine Setup
echo Role: %ROLE%
echo MQTT Broker: %BROKER_IP%:1883
echo ============================================
echo.

REM Check if Python is available
py --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Please install Python.
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
py -m pip install -r requirements.txt >nul 2>&1
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    exit /b 1
)
echo OK - Dependencies installed

REM Set environment variables
echo [2/3] Setting up environment...
set MQTT_BROKER=%BROKER_IP%
set MQTT_PORT=1883

REM Create/update .env file with new MQTT settings
echo Updating .env file...
(
    echo # MQTT Broker configuration
    echo MQTT_BROKER=%BROKER_IP%
    echo MQTT_PORT=1883
    echo.
    echo # IoT Ingestion topics
    echo RAW_TOPIC=smart-campus/raw/iot/environment
    echo PROCESSED_TOPIC=smart-campus/events/sensor
    echo DEVICE_REGISTRY=device_registry.csv
    echo.
    echo # Core Business topics
    echo SENSOR_TOPIC=smart-campus/events/sensor
    echo ACCESS_TOPIC=smart-campus/events/access
    echo CAMERA_TOPIC=smart-campus/events/camera
    echo ALERT_TOPIC=smart-campus/events/alert
    echo ANALYTICS_TOPIC=smart-campus/events/analytics
    echo RULES_FILE=core_business_rules.json
) > .env.tmp
move /y .env.tmp .env >nul 2>&1

echo OK - Environment configured

REM Run the appropriate service
echo [3/3] Starting service...
echo.

if "%ROLE%"=="iot" (
    echo Starting IoT Ingestion Service...
    echo Connected to MQTT broker at %BROKER_IP%:1883
    echo Subscribing to: smart-campus/raw/iot/environment
    echo Publishing to: smart-campus/events/sensor
    echo.
    py src/iot_ingestion.py
) else if "%ROLE%"=="core" (
    echo Starting Core Business Service...
    echo Connected to MQTT broker at %BROKER_IP%:1883
    echo Subscribing to sensor/access/camera events
    echo Publishing alerts to: smart-campus/events/alert
    echo.
    py src/core_business_service.py
) else if "%ROLE%"=="demo" (
    echo Publishing demo IoT events...
    echo Target MQTT broker: %BROKER_IP%:1883
    echo.
    py demo_iot_to_core.py
) else (
    echo ERROR: Unknown role '%ROLE%'
    echo Valid roles: iot, core, demo
    exit /b 1
)
