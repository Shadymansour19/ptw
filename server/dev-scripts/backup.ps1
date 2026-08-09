<#
Backs up the PTW database and server-side file storage (MIWI docs + PTW/IC
attachments) into a single timestamped directory. Prunes backups older than
$RetentionDays. Windows equivalent of backup.sh - produces the exact same
<db>.dump / files.tar.gz layout, so backups/restores are interchangeable
between this and the Linux scripts.

Requires on PATH: pg_dump.exe (ships with the PostgreSQL Windows installer,
e.g. C:\Program Files\PostgreSQL\16\bin) and tar.exe (built into Windows 10
1803+ / Server 2019+ at C:\Windows\System32\tar.exe).

Usage: .\backup.ps1 [-BackupRoot "D:\ptw-backups"]
  -BackupRoot defaults to paths.BACKUP_DIR (the same on-disk location the
  in-app Admin "Backups" tab / POST /backups already writes to - see
  server/backupService.py). Pass an explicit path to back up somewhere else
  (e.g. off this machine's disk entirely, which is the point of running this
  on a schedule rather than relying on the in-app button alone).
#>
param(
    [string]$BackupRoot
)

$ErrorActionPreference = "Stop"

$ServerDir = Split-Path -Parent $PSScriptRoot
Push-Location $ServerDir
try {
    $PtwPaths = (python -c "from paths import DATA_DIR, BACKUP_DIR; print(DATA_DIR); print(BACKUP_DIR)")
    $DataDir = $PtwPaths[0]
    if (-not $BackupRoot) { $BackupRoot = $PtwPaths[1] }
}
finally { Pop-Location }
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

# .env lives beside the code (ServerDir); MIWI docs + grouped PTW/IC attachment folders
# (ptws/, ics/) live under DataDir (server/paths.py) - tar.exe (bsdtar) accepts multiple -C
# switches to pull members from different real directories into one archive, and adding a
# directory pulls in its contents recursively.
Write-Host "[$Timestamp] Archiving file storage..."
Push-Location $DataDir
try {
    $dataTargets = @()
    if (Test-Path "miwi") { $dataTargets += "miwi" }
    if (Test-Path "ptws") { $dataTargets += "ptws" }
    if (Test-Path "ics") { $dataTargets += "ics" }
    & tar.exe -czf (Join-Path $Dest "files.tar.gz") -C $ServerDir ".env" -C $DataDir @dataTargets
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
