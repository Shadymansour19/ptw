<#
Restores a PTW backup produced by backup.ps1 (or the Linux backup.sh - the
dump/tar.gz format is identical on both platforms). DESTRUCTIVE: drops and
recreates the database, and overwrites file-storage directories. Stop the
server before running this.

Requires on PATH: dropdb.exe / createdb.exe / pg_restore.exe (PostgreSQL
Windows installer bin folder) and tar.exe (built into Windows 10 1803+ /
Server 2019+).

Usage: .\restore.ps1 -BackupDir "C:\ptw-backups\20260801_192841"
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupDir
)

$ErrorActionPreference = "Stop"

$ServerDir = Split-Path -Parent $PSScriptRoot
Push-Location $ServerDir
try { $DataDir = (python -c "from paths import DATA_DIR; print(DATA_DIR)") }
finally { Pop-Location }

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

$DumpFile = Join-Path $BackupDir "$DbName.dump"
$FilesArchive = Join-Path $BackupDir "files.tar.gz"
if (-not (Test-Path $DumpFile)) { throw "No $DbName.dump in $BackupDir" }
if (-not (Test-Path $FilesArchive)) { throw "No files.tar.gz in $BackupDir" }

Write-Host "This will DROP the current '$DbName' database and overwrite file storage in $DataDir (and .env in $ServerDir)."
$confirm = Read-Host "Type 'yes' to continue"
if ($confirm -ne "yes") { Write-Host "Aborted."; exit 1 }

$env:PGPASSWORD = $DbPassword

Write-Host "Restoring database..."
& dropdb.exe -h $DbHost -U $DbUser --if-exists $DbName
& createdb.exe -h $DbHost -U $DbUser $DbName
& pg_restore.exe -h $DbHost -U $DbUser -d $DbName $DumpFile
if ($LASTEXITCODE -ne 0) { Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue; throw "pg_restore failed" }

Remove-Item Env:\PGPASSWORD -ErrorAction SilentlyContinue

Write-Host "Restoring file storage..."
# The archive is flat (.env alongside miwi/ and *-attachments/) but those now live in two
# different real directories - extract to a scratch dir, then route each entry home.
$TmpExtract = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
New-Item -ItemType Directory -Path $TmpExtract | Out-Null
try {
    & tar.exe -xzf $FilesArchive -C $TmpExtract
    if ($LASTEXITCODE -ne 0) { throw "tar extract failed" }

    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
    $EnvEntry = Join-Path $TmpExtract ".env"
    if (Test-Path $EnvEntry) { Move-Item -Force $EnvEntry (Join-Path $ServerDir ".env") }
    Get-ChildItem $TmpExtract -Force | ForEach-Object {
        $dest = Join-Path $DataDir $_.Name
        if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
        Move-Item $_.FullName $dest
    }
}
finally {
    Remove-Item $TmpExtract -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Restore complete. Start the server again."
