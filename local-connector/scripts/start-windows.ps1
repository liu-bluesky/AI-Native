$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RootDir

$HostValue = if ($env:LOCAL_CONNECTOR_HOST) { $env:LOCAL_CONNECTOR_HOST } else { "127.0.0.1" }
$PortValue = if ($env:LOCAL_CONNECTOR_PORT) { $env:LOCAL_CONNECTOR_PORT } else { "3931" }

$env:LOCAL_CONNECTOR_HOST = $HostValue
$env:LOCAL_CONNECTOR_PORT = $PortValue

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  Write-Host "未检测到 Node.js，请先安装 Node.js 18 或更高版本。"
  Write-Host "下载地址：https://nodejs.org/"
  Read-Host "按回车键退出"
  exit 1
}

node .\launcher.js

Write-Host ""
Write-Host "Local Connector 已停止。"
Write-Host "如需排查，请查看 logs/bootstrap.log 和 logs/connector.log"
Read-Host "按回车键关闭窗口"
