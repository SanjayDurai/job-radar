# Local development Postgres (port 5433), using the PostgreSQL install already on this machine.
# Usage:  .\scripts\localdb.ps1 start | stop | status | init
# Data lives in .localdb\ (git-ignored). Production uses Neon instead.
param([ValidateSet("start", "stop", "status", "init")][string]$Action = "status")

$pg = "C:\Program Files\PostgreSQL\18\bin"
$root = Split-Path -Parent $PSScriptRoot
$data = Join-Path $root ".localdb"
$log = Join-Path $root ".localdb.log"   # outside the data dir, so startup never hits a locked file

switch ($Action) {
    "init" {
        & "$pg\initdb.exe" -D $data -U radar --auth=trust -E UTF8 --locale=C
        & $PSCommandPath start
        & "$pg\createdb.exe" -h localhost -p 5433 -U radar radar
        & "$pg\createdb.exe" -h localhost -p 5433 -U radar radar_test
    }
    "start" {
        Start-Process -FilePath "$pg\pg_ctl.exe" -ArgumentList "start", "-D", "`"$data`"", "-o", "`"-p 5433`"", "-l", "`"$log`"" -WindowStyle Hidden
        for ($i = 0; $i -lt 30; $i++) {
            & "$pg\pg_isready.exe" -h localhost -p 5433 -q
            if ($LASTEXITCODE -eq 0) { Write-Output "Local Postgres is running on port 5433."; return }
            Start-Sleep -Seconds 1
        }
        Write-Output "Postgres did not start in 30s; see $log"
    }
    "stop" { & "$pg\pg_ctl.exe" stop -D $data -m fast }
    "status" { & "$pg\pg_isready.exe" -h localhost -p 5433 }
}
