#requires -Version 5.1
<#
.SYNOPSIS
  Secure first-run credential setup, performed entirely on your Windows laptop.
.NOTES
  Never commit .env or secrets/client_secret.json.
#>
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)

if (!(Test-Path .env)) { Copy-Item .env.example .env }
if (!(Test-Path secrets)) { New-Item -ItemType Directory secrets | Out-Null }

function Get-Secret([string] $Prompt) {
    $value = Read-Host -Prompt $Prompt -AsSecureString
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($value)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
}

Write-Host "Google OAuth credentials are different from a Gemini API key." -ForegroundColor Cyan
Write-Host "Enter credentials ONLY in these local prompts. They won't be uploaded to GitHub." -ForegroundColor Yellow
$clientId = Read-Host 'Google OAuth Desktop Client ID (ends in apps.googleusercontent.com)'
$clientSecret = Get-Secret 'Google OAuth Client Secret (GOCSPX-...)'
$geminiKey = Get-Secret 'Gemini API key (AQ...)'

if (!$clientId.EndsWith('.apps.googleusercontent.com')) { throw 'Invalid Google OAuth Client ID.' }
if (!$clientSecret.StartsWith('GOCSPX-')) { throw 'Unexpected Google OAuth Client Secret format. Check the OAuth Desktop client in Google Cloud.' }
if (!$geminiKey) { throw 'Gemini API key is required.' }

# Python google-auth-oauthlib InstalledAppFlow expects a Desktop OAuth installed object.
# File stays in gitignored secrets/.
$client = @{
    installed = @{
        client_id = $clientId.Trim()
        project_id = 'meow-meow-arena'
        auth_uri = 'https://accounts.google.com/o/oauth2/auth'
        token_uri = 'https://oauth2.googleapis.com/token'
        auth_provider_x509_cert_url = 'https://www.googleapis.com/oauth2/v1/certs'
        client_secret = $clientSecret
        redirect_uris = @('http://localhost')
    }
}
$client | ConvertTo-Json -Depth 6 | Set-Content -Path 'secrets/client_secret.json' -Encoding UTF8

$envFile = '.env'
$lines = Get-Content $envFile
$fields = @{
    LLM_PROVIDER = 'gemini'
    GEMINI_API_KEY = $geminiKey
    GEMINI_MODEL = 'gemini-3.8-flash'
    GOOGLE_OWNER_EMAIL = 'syedaalizahassannaqvi@gmail.com'
    JUDGE_EMAIL = 'syedaalizahassannaqvi@gmail.com'
}
# Configure distinct strong random secrets for the private app-to-n8n channel.
$existing = @{}
foreach ($line in $lines) {
    if ($line -match '^([A-Za-z_][A-Za-z_0-9]*)=(.*)$') { $existing[$matches[1]]=$matches[2] }
}
foreach ($key in @('INTERNAL_API_KEY', 'N8N_ENCRYPTION_KEY')) {
    if (!$existing.ContainsKey($key) -or !$existing[$key] -or $existing[$key].StartsWith('replace-with')) {
        $buffer = New-Object byte[] 36
        [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($buffer)
        $fields[$key] = [Convert]::ToBase64String($buffer).Replace('+','-').Replace('/','_').TrimEnd('=')
    }
}
$keys = New-Object 'System.Collections.Generic.HashSet[string]'
$output = New-Object 'System.Collections.Generic.List[string]'
foreach ($line in $lines) {
    if ($line -match '^([A-Za-z_][A-Za-z_0-9]*)=') {
        $name = $matches[1]
        if ($fields.ContainsKey($name)) {
            $output.Add("$name=$($fields[$name])")
            [void]$keys.Add($name)
            continue
        }
    }
    $output.Add($line)
}
foreach ($name in $fields.Keys) {
    if (!$keys.Contains($name)) { $output.Add("$name=$($fields[$name])") }
}
$output | Set-Content -Path $envFile -Encoding UTF8
Write-Host 'Configuration saved locally in .env and secrets/client_secret.json.' -ForegroundColor Green
Write-Host 'Next command: .\scripts\start-demo.ps1' -ForegroundColor Green
