param(
    [string]$EnvPath = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\.env'))
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $EnvPath -PathType Leaf)) {
    throw 'Repository .env is missing. Run scripts\up.cmd or scripts\setup-local.ps1 first.'
}

$values = @{}
foreach ($line in [System.IO.File]::ReadAllLines($EnvPath)) {
    if ($line -match '^\s*#' -or [string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -notmatch '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        throw 'Repository .env contains a malformed line. Use NAME=value on one line per setting.'
    }
    $values[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
}

foreach ($name in @('DEEPSEEK_API_KEY', 'ENGINE_INTERNAL_TOKEN', 'DB_PASSWORD', 'MYSQL_ROOT_PASSWORD')) {
    $value = [string]$values[$name]
    if (-not $value -or $value.StartsWith('replace-with-')) {
        throw "Repository .env has no usable $name. Edit .env or remove placeholder values."
    }
}

Write-Host 'Repository .env contains the four required settings; values were not displayed.'
