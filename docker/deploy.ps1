param(
  [Parameter(Position=0)]
  [ValidateSet('pull','up','deploy','ps','logs','down','backup-db','restore-db')]
  [string]$Action = 'deploy',

  [Parameter(Position=1)]
  [string]$Arg = ''
)

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ComposeFile = if ($env:COMPOSE_FILE) { $env:COMPOSE_FILE } else { Join-Path $ScriptDir 'compose.prod.yml' }
$EnvFile = if ($env:ENV_FILE) { $env:ENV_FILE } else { Join-Path $ScriptDir '.env.prod' }
$BackupDir = if ($env:BACKUP_DIR) { $env:BACKUP_DIR } else { Join-Path $ScriptDir 'backup' }
$PostgresContainer = if ($env:POSTGRES_CONTAINER) { $env:POSTGRES_CONTAINER } else { 'ai-employee-postgres' }

function Require-Docker {
  docker --version | Out-Null
  docker compose version | Out-Null
}

function Compose {
  docker compose --env-file $EnvFile -f $ComposeFile @args
}

function Require-Config {
  if (!(Test-Path $ComposeFile)) { throw "compose file not found: $ComposeFile" }
  if (!(Test-Path $EnvFile)) { throw "env file not found: $EnvFile. Copy .env.prod.example to .env.prod first." }
  New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
}

function Read-EnvValue([string]$Name, [string]$Default) {
  if (!(Test-Path $EnvFile)) { return $Default }
  $line = Get-Content $EnvFile | Where-Object { $_ -match "^$Name=" } | Select-Object -First 1
  if (!$line) { return $Default }
  return ($line -split '=', 2)[1]
}

Require-Docker
Require-Config

switch ($Action) {
  'pull' { Compose pull }
  'up' { Compose up -d }
  'deploy' { Compose pull; Compose up -d }
  'ps' { Compose ps }
  'logs' { if ($Arg) { Compose logs -f $Arg } else { Compose logs -f } }
  'down' { Compose down }
  'backup-db' {
    $OutputFile = if ($Arg) { $Arg } else { Join-Path $BackupDir 'ai_employee.sql' }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputFile) | Out-Null
    $DbUser = Read-EnvValue 'DB_USER' 'admin'
    $DbName = Read-EnvValue 'DB_NAME' 'ai_employee'
    docker exec $PostgresContainer pg_dump -U $DbUser $DbName | Out-File -Encoding utf8 $OutputFile
    Write-Host "db backup written to $OutputFile"
  }
  'restore-db' {
    if (!$Arg -or !(Test-Path $Arg)) { throw 'restore-db requires an existing sql file' }
    $DbUser = Read-EnvValue 'DB_USER' 'admin'
    $DbName = Read-EnvValue 'DB_NAME' 'ai_employee'
    Get-Content $Arg | docker exec -i $PostgresContainer psql -U $DbUser -d $DbName
    Write-Host "db restored from $Arg"
  }
}
