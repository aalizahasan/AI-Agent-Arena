#requires -Version 5.1
<#
.SYNOPSIS
  Meow Meow AI Arena - Windows competition launcher.
.DESCRIPTION
  Runs the automated tests, Google OAuth bootstrap, starts Docker, and checks integration health.
  Requires Docker Desktop, Python 3.12 and a Google Cloud Desktop OAuth client file.
#>
param(
  [switch]$SkipBootstrap,
  [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

function Step([string]$Message) {
  Write-Host ("`n==> " + $Message) -ForegroundColor Cyan
}
function Fail([string]$Message) {
  throw $Message
}

Step 'Checking prerequisites'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  Fail 'Docker Desktop is not installed.'
}
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  Fail 'Python 3.12 is not available on PATH.'
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
  Fail 'Docker Desktop is not running. Start Docker Desktop first.'
}

if (-not (Test-Path '.env')) {
  Copy-Item '.env.example' '.env'
  Fail 'Created .env. Fill GEMINI_API_KEY, INTERNAL_API_KEY and N8N_ENCRYPTION_KEY, then rerun.'
}

$envText = Get-Content '.env' -Raw
$provider = 'gemini'
if ($envText -match '(?m)^LLM_PROVIDER\s*=\s*openai\s*$') {
  $provider = 'openai'
}
$llmKey = if ($provider -eq 'gemini') { 'GEMINI_API_KEY' } else { 'OPENAI_API_KEY' }
foreach ($key in @($llmKey, 'INTERNAL_API_KEY', 'N8N_ENCRYPTION_KEY')) {
  $line = [regex]::Match($envText, "(?m)^$key\s*=\s*(.+)\s*$")
  if (-not $line.Success -or $line.Groups[1].Value.Trim() -match '^(replace-with|$)') {
    Fail "Configure $key in .env. Never paste secrets into chat."
  }
}

if (-not (Test-Path 'secrets')) {
  New-Item -ItemType Directory 'secrets' | Out-Null
}
if (-not (Test-Path '.venv\Scripts\python.exe')) {
  Step 'Creating virtual environment'
  python -m venv .venv
  if ($LASTEXITCODE -ne 0) { Fail 'Virtual environment creation failed.' }
}
$python = Join-Path (Get-Location) '.venv\Scripts\python.exe'

Step 'Installing Python dependencies'
& $python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { Fail 'Python package installation failed.' }

if (-not $SkipTests) {
  Step 'Running agent tests'
  & $python -m pytest -q
  if ($LASTEXITCODE -ne 0) { Fail 'Tests failed; do not demo yet.' }
}

if (-not $SkipBootstrap) {
  if (-not (Test-Path 'secrets\client_secret.json') -and -not (Test-Path 'secrets\token.json')) {
    Fail 'Google Desktop OAuth JSON missing at secrets\client_secret.json. Configure Google Cloud OAuth first.'
  }
  Step 'Checking authorized Google account and creating/reusing demo resources'
  & $python -m scripts.bootstrap_google
  if ($LASTEXITCODE -ne 0) { Fail 'Google resource bootstrap failed.' }
}

Step 'Launching Docker services'
docker compose up -d --build
if ($LASTEXITCODE -ne 0) { Fail 'Docker Compose startup failed.' }

Step 'Checking integrations (read-only)'
& $python -m scripts.preflight
if ($LASTEXITCODE -ne 0) {
  Write-Warning 'Preflight failed. Read the error above before judging.'
}
Write-Host ''
Write-Host 'Customer interface: http://localhost:8000' -ForegroundColor Green
Write-Host 'n8n editor:        http://localhost:5678' -ForegroundColor Green
Write-Host 'IMPORT AND PUBLISH workflows/mmvh-front-desk.json IN n8n.' -ForegroundColor Yellow
Write-Host 'Perform a real Google Calendar booking and verify the Sheets row before the demo.' -ForegroundColor Yellow
