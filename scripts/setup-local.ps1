param()

$ErrorActionPreference = 'Stop'
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$envPath = Join-Path $repoRoot '.env'
if (Test-Path -LiteralPath $envPath) {
    Write-Host 'Repository .env already exists; leaving it unchanged.'
    exit 0
}

function Read-DotEnvValue([string]$path, [string]$name) {
    if (-not (Test-Path -LiteralPath $path)) { return '' }
    foreach ($line in [System.IO.File]::ReadAllLines($path)) {
        if ($line.StartsWith("$name=")) {
            return $line.Substring($name.Length + 1).Trim().Trim('"').Trim("'")
        }
    }
    return ''
}

function New-LocalSecret {
    $bytes = New-Object byte[] 32
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$legacyEnv = Join-Path $repoRoot 'paper4_pipeline\.env'
$key = Read-DotEnvValue $legacyEnv 'DEEPSEEK_API_KEY'
if (-not $key -or $key.StartsWith('replace-with-')) {
    $secure = Read-Host 'DeepSeek API key (input hidden)' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}
if (-not $key -or $key.Contains("`n") -or $key.Contains("`r")) {
    throw 'A non-empty, single-line DeepSeek API key is required.'
}

$token = Read-DotEnvValue $legacyEnv 'ENGINE_INTERNAL_TOKEN'
if (-not $token -or $token.StartsWith('replace-with-')) { $token = New-LocalSecret }

$lines = @(
    '# Local-only credentials. Do not commit this file.'
    "DEEPSEEK_API_KEY=$key"
    'DEEPSEEK_BASE_URL=https://api.deepseek.com'
    "ENGINE_INTERNAL_TOKEN=$token"
    "DB_PASSWORD=$(New-LocalSecret)"
    "MYSQL_ROOT_PASSWORD=$(New-LocalSecret)"
)
$encoding = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($envPath, (($lines -join "`n") + "`n"), $encoding)
Write-Host 'Created ignored repository .env. Existing paper4_pipeline/.env was not changed.'
Write-Host 'Docker uses a separate MySQL volume on host port 3307; old local MySQL data is untouched.'
