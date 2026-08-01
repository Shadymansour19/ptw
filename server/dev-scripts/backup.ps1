<#
Backs up the PTW database and server-side file storage (MIWI docs + PTW/IC
attachments) into a single timestamped directory. Prunes backups older than
$RetentionDays. Windows equivalent of backup.sh - produces the exact same
<db>.dump / files.tar.gz layout, so backups/restores are interchangeable
between this and the Linux scripts.

Requires on PATH: pg_dump.exe (ships with the PostgreSQL Windows installer,
e.g. C:\Program Files\PostgreSQL\16\bin) and tar.exe (built into Windows 10
1803+ / Server 2019+ at C:\Windows\System32\tar.exe).

Usage: .\backup.ps1 [-BackupRoot "C:\ptw-backups"]
#>
param(
    [string]$BackupRoot = "C:\ptw-backups"
)

$ErrorActionPreference = "Stop"

$ServerDir = Split-Path -Parent $PSScriptRoot
$RetentionDays = 14
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Dest = Join-Path $BackupRoot $Timestamp

function Get-EnvValue($Key, $Path) {
    $line = Get-Content $Path | Where-Object { $_ -match "^$Key=" } | Select-Object -First 1
    if ($null -eq $line) { throw "Missing $Key in $Path" }
    return $line.Substring($Key.Length + 1)
}

$EnvPath = Join-Path $ServerDir ".env"
$DbHost = Get-EnvValue "DB_HOST" $EnvPath
$DbName = Get-EnvValue "DB_NAME" $EnvPath
$DbUser = Get-EnvValue "DB_USER" $EnvPath
$DbPassword = Get-EnvValue "DB_PASSWORD" $EnvPath

New-Item -ItemType Directory -Path $Dest -Force | Out-Null

Write-Host "[$Timestamp] Dumping database $DbName..."
$env:PGPASSWORD = $DbPassword
& pg_dump.exe -h $DbHost -U $DbUser -d $DbName -Fc -f (Join-Path $Dest "$DbName.dump")
if ($LASTEXITCODE -ne 0) { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue; throw "pg_dump failed" }

Write-Host "[$Timestamp] Archiving file storage..."
Push-Location $ServerDir
try {
    $targets = @(".env")
    if (Test-Path "miwi") { $targets += "miwi" }
    $targets += (Get-ChildItem -Directory -Filter "ptw-*-attachments" -ErrorAction SilentlyContinue).Name
    $targets += (Get-ChildItem -Directory -Filter "ic-*-attachments" -ErrorAction SilentlyContinue).Name
    & tar.exe -czf (Join-Path $Dest "files.tar.gz") @targets
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
}
finally {
    Pop-Location
}

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

Write-Host "[$Timestamp] Backup complete: $Dest"
$sizeMb = (Get-ChildItem $Dest | Measure-Object -Property Length -Sum).Sum / 1MB
Write-Host ("{0:N1} MB" -f $sizeMb)

Get-ChildItem $BackupRoot -Directory | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$RetentionDays) } | ForEach-Object {
    Write-Host "Pruning old backup: $($_.FullName)"
    Remove-Item $_.FullName -Recurse -Force
}
