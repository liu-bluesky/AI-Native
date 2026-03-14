@echo off
setlocal

set ROOT_DIR=%~dp0..
cd /d "%ROOT_DIR%"

title Local Connector
if "%LOCAL_CONNECTOR_HOST%"=="" set "LOCAL_CONNECTOR_HOST=127.0.0.1"
if "%LOCAL_CONNECTOR_PORT%"=="" set "LOCAL_CONNECTOR_PORT=3931"

where node >nul 2>nul
if errorlevel 1 (
  echo 未检测到 Node.js，请先安装 Node.js 18 或更高版本。
  echo 下载地址：https://nodejs.org/
  pause
  exit /b 1
)

node launcher.js
echo.
echo Local Connector 已停止。
echo 如需排查，请查看 logs\bootstrap.log 和 logs\connector.log
pause
