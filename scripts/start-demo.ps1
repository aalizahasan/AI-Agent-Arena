#requires -Version 5.1
<#
.SYNOPSIS
  Meow Meow Arena demo setup for Windows PowerShell.
.DESCRIPTION
  Installs project Python packages, performs local Google OAuth bootstrap,
  starts Docker services and checks read-only integration health.
  Secrets stay on your computer. Does not publish n8n or claim real bookings.
#>
param([switch]$SkipBootstrap,[switch]$SkipTests)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
function Step([string]$message){ Write-Host ("`n==> " + $message) -ForegroundColor Cyan }
function StopWith([string]$message){ throw $message }
Step 'Checking prerequisites'
if(-not (Get-Command docker -ErrorAction SilentlyContinue)){StopWith 'Install and start Docker Desktop before running this script.'}
if(-not (Get-Command python -ErrorAction SilentlyContinue)){StopWith 'Install Python 3.12 and ensure python is on PATH.'}
docker info *> $null
if($LASTEXITCODE -ne 0){StopWith 'Docker Desktop is not running.'}
if(-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  StopWith 'Created .env. Fill OPENAI_API_KEY, INTERNAL_API_KEY, N8N_ENCRYPTION_KEY and JUDGE_EMAIL, then rerun. Never commit .env.'
}
$envText = Get-Content '.env' -Raw
foreach($key in @('OPENAI_API_KEY','INTERNAL_API_KEY','N8N_ENCRYPTION_KEY')){
  if($envText -notmatch "(?m)^$key\s*=\s*[^#\r\n ]" -or $envText -match "(?m)^$key\s*=\s*replace-with") {
    StopWith "Please set $key in .env (do not post credentials in chat)."
  }
}
if(-not (Test-Path 'secrets')){New-Item -ItemType Directory 'secrets' | Out-Null}
if(-not (Test-Path '.venv/Scripts/python.exe')){
  Step 'Creating isolated Python environment'
  python -m venv .venv
}
$python = Join-Path (Get-Location) '.venv/Scripts/python.exe'
Step 'Installing project dependencies'
& $python -m pip install -r requirements.txt
if($LASTEXITCODE -ne 0){StopWith 'Python dependency installation failed.'}
if(-not $SkipTests){
  Step 'Running isolated tests'
  & $python -m pytest -q
  if($LASTEXITCODE -ne 0){StopWith 'Tests failed. Do not demo until fixed.'}
}
if(-not $SkipBootstrap){
  if(-not (Test-Path 'secrets/client_secret.json') -and -not (Test-Path 'secrets/token.json')){
    StopWith 'Download Google Cloud Desktop OAuth JSON to secrets/client_secret.json and rerun.'
  }
  Step 'Creating or reusing official Google calendars and spreadsheet'
  & $python -m scripts.bootstrap_google
  if($LASTEXITCODE -ne 0){StopWith 'Google resource bootstrap failed.'}
}
Step 'Starting n8n and agent services'
docker compose up -d --build
if($LASTEXITCODE -ne 0){StopWith 'Docker Compose startup failed.'}
Step 'Running read-only live environment checks'
& $python -m scripts.preflight
if($LASTEXITCODE -ne 0) {
  Write-Warning 'Preflight detected a blocker. Read the error above; do not claim live readiness.'
}
Write-Host '`nCustomer page: http://localhost:8000' -ForegroundColor Green
Write-Host 'n8n editor:    http://localhost:5678' -ForegroundColor Green
Write-Host 'IMPORTANT: Import/publish workflows/mmvh-front-desk.json in n8n before running live requests.' -ForegroundColor Yellow
Write-Host 'Required final proof: create real Calendar event, ACTIVE Sheets row, cancel and verify CANCELED.' -ForegroundColor Yellow
