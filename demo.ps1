#Requires -Version 5.1
<#
.SYNOPSIS
    harmoni Revenue Intelligence -- one-command demo launcher.

.DESCRIPTION
    1.  Kills every process currently occupying an app port.
    2.  Loads .env into the current process environment.
    3.  Verifies Docker is running.
    4.  Discovers the virtualenv Python executable.
    5.  Starts all Docker Compose services.
    6.  Waits for PostgreSQL, Redis, ClickHouse, Zookeeper, Kafka, and Schema
        Registry to report healthy.
    7.  Applies SQL migrations in dependency order via docker exec.
    8.  Opens a new PowerShell window for the FastAPI server (port 8000).
    9.  Opens a new PowerShell window for the Next.js dashboard (port 3000).
    10. Waits for the API to respond, then opens the browser.
    11. Prints a URL summary.

.EXAMPLE
    .\demo.ps1
#>

# ---- Bootstrap --------------------------------------------------------------

$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $RepoRoot

# ---- Color helpers ----------------------------------------------------------

function Write-Step { param([string]$Msg)
    Write-Host ""
    Write-Host "  >> $Msg" -ForegroundColor Cyan
}
function Write-Ok   { param([string]$Msg) Write-Host "  OK  $Msg" -ForegroundColor Green  }
function Write-Warn { param([string]$Msg) Write-Host "  !!  $Msg" -ForegroundColor Yellow }
function Write-Fail { param([string]$Msg) Write-Host "  XX  $Msg" -ForegroundColor Red    }

function Exit-Script {
    param([string]$Reason)
    Write-Fail $Reason
    Read-Host "`n  Press Enter to exit"
    exit 1
}

# ---- Banner -----------------------------------------------------------------

Write-Host ""
Write-Host "  ======================================================" -ForegroundColor DarkCyan
Write-Host "     harmoni  --  Revenue Intelligence Demo Launcher    " -ForegroundColor Cyan
Write-Host "  ======================================================" -ForegroundColor DarkCyan
Write-Host ""

# =============================================================================
# STEP 1 -- Kill processes on app ports (FastAPI + Next.js only)
# =============================================================================
#
# Only clears the two processes we launch ourselves. Docker service ports
# (PostgreSQL, Redis, Kafka, etc.) are left untouched so a running stack
# is not disrupted between demo runs.

$AppPorts = @(8000, 3000)

Write-Step "Clearing app ports: $($AppPorts -join '  ')"

foreach ($port in $AppPorts) {
    $matchedLines = netstat -ano 2>$null | Where-Object { $_ -match ":$port\s" }

    foreach ($line in $matchedLines) {
        $parts  = ($line.Trim()) -split '\s+'
        $pidStr = $parts[-1]

        if ($pidStr -match '^\d+$') {
            $pidInt = [int]$pidStr
            if ($pidInt -le 4) { continue }

            try {
                Stop-Process -Id $pidInt -Force -ErrorAction SilentlyContinue
                Write-Warn "  Killed PID $pidInt (was on :$port)"
            } catch { }
        }
    }
}

Write-Ok "App ports cleared"

# =============================================================================
# STEP 2 -- Load .env
# =============================================================================

Write-Step "Loading environment variables"

$EnvFile = Join-Path $RepoRoot '.env'

if (-not (Test-Path $EnvFile)) {
    $ExampleFile = Join-Path $RepoRoot '.env.example'
    if (Test-Path $ExampleFile) {
        Copy-Item $ExampleFile $EnvFile
        Write-Warn ".env not found -- copied from .env.example"
        Write-Warn "Set API_SECRET_KEY and HARMONI_ADMIN_TOKEN in .env before production use"
    } else {
        Exit-Script ".env and .env.example are both missing from $RepoRoot"
    }
}

$envVarsLoaded = 0
Get-Content $EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line -match '^\s*#') { return }

    if ($line -match '^([^=]+)=(.*)$') {
        $key   = $matches[1].Trim()
        $value = $matches[2].Trim()
        $value = $value -replace '^[''"]|[''"]$', ''
        [System.Environment]::SetEnvironmentVariable($key, $value, 'Process')
        $envVarsLoaded++
    }
}

Write-Ok "$envVarsLoaded variables loaded from .env"

# =============================================================================
# STEP 3 -- Verify Docker daemon
# =============================================================================

Write-Step "Checking Docker daemon"

$dockerReady = $false
for ($attempt = 1; $attempt -le 18; $attempt++) {
    docker info > $null 2> $null
    if ($LASTEXITCODE -eq 0) { $dockerReady = $true; break }
    $elapsed = ($attempt - 1) * 5
    Write-Warn "Docker not yet ready -- ${elapsed}s elapsed (will keep trying up to 90s) ..."
    Start-Sleep 5
}
if (-not $dockerReady) {
    Exit-Script "Docker did not become ready after 90s. Open Docker Desktop, wait for the tray icon to stop animating, then retry."
}

Write-Ok "Docker is running"

# =============================================================================
# STEP 4 -- Locate Python executable
# =============================================================================

Write-Step "Locating Python"

$pythonExe = $null

$venvCandidates = @(
    (Join-Path $RepoRoot '.venv\Scripts\python.exe'),
    (Join-Path $RepoRoot  'venv\Scripts\python.exe')
)

foreach ($candidate in $venvCandidates) {
    if (Test-Path $candidate) {
        $pythonExe = $candidate
        break
    }
}

if (-not $pythonExe) {
    $sysPython = Get-Command python -ErrorAction SilentlyContinue
    if ($sysPython) {
        $pythonExe = $sysPython.Source
        Write-Warn "No virtualenv found -- using system Python at $pythonExe"
        Write-Warn "Run: uv venv && .venv\Scripts\activate && uv pip install -e '.[all,dev]'"
    }
}

if (-not $pythonExe) {
    Exit-Script "Python not found. Run: uv venv && .venv\Scripts\activate && uv pip install -e '.[all,dev]'"
}

$pyVersion = & $pythonExe --version 2>&1
Write-Ok "$pyVersion  ->  $pythonExe"

# =============================================================================
# STEP 5 -- docker compose up
# =============================================================================

Write-Step "Removing any existing harmoni containers (volumes preserved)"

docker compose down 2>$null
Write-Ok "Previous containers removed"

Write-Step "Starting Docker Compose services"

docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Exit-Script "docker compose up failed (exit code $LASTEXITCODE)"
}

Write-Ok "Compose services started"

# =============================================================================
# STEP 6 -- Wait for services to be ready
# =============================================================================

function Wait-ContainerHealthy {
    param(
        [Parameter(Mandatory)][string]$ContainerName,
        [int]$TimeoutSec = 120
    )

    Write-Step "Waiting for $ContainerName to be healthy (up to ${TimeoutSec}s)"

    $deadline = (Get-Date).AddSeconds($TimeoutSec)

    while ((Get-Date) -lt $deadline) {
        $status = docker inspect --format '{{.State.Health.Status}}' $ContainerName 2>$null
        if ($status) { $status = $status.Trim() }

        switch ($status) {
            'healthy'   { Write-Ok "$ContainerName is healthy"; return }
            'unhealthy' { Exit-Script "$ContainerName is unhealthy. Check: docker logs $ContainerName" }
            default     { Write-Host "    $ContainerName  [$status] ..." -ForegroundColor DarkGray }
        }

        Start-Sleep 3
    }

    Exit-Script "$ContainerName did not become healthy in ${TimeoutSec}s. Check: docker logs $ContainerName"
}

function Wait-ContainerRunning {
    param(
        [Parameter(Mandatory)][string]$ContainerName,
        [int]$TimeoutSec    = 60,
        [int]$ExtraDelaySec = 3
    )

    Write-Step "Waiting for $ContainerName to be running (up to ${TimeoutSec}s)"

    $deadline = (Get-Date).AddSeconds($TimeoutSec)

    while ((Get-Date) -lt $deadline) {
        $status = docker inspect --format '{{.State.Status}}' $ContainerName 2>$null
        if ($status) { $status = $status.Trim() }

        if ($status -eq 'running') {
            Write-Ok "$ContainerName is running"
            if ($ExtraDelaySec -gt 0) {
                Write-Host "    Settling for ${ExtraDelaySec}s ..." -ForegroundColor DarkGray
                Start-Sleep $ExtraDelaySec
            }
            return
        }

        Write-Host "    $ContainerName  [$status] ..." -ForegroundColor DarkGray
        Start-Sleep 3
    }

    Exit-Script "$ContainerName did not start in ${TimeoutSec}s. Check: docker logs $ContainerName"
}

# Core data services -- must be healthy before migrations run
Wait-ContainerHealthy -ContainerName 'harmoni-postgres'    -TimeoutSec 120
Wait-ContainerHealthy -ContainerName 'harmoni-redis'       -TimeoutSec  60
Wait-ContainerHealthy -ContainerName 'harmoni-clickhouse'  -TimeoutSec  90
Wait-ContainerHealthy -ContainerName 'harmoni-zookeeper'   -TimeoutSec  60
Wait-ContainerHealthy -ContainerName 'harmoni-kafka'       -TimeoutSec 120
Wait-ContainerHealthy -ContainerName 'harmoni-schema-registry' -TimeoutSec 90

# Kafka UI has no HEALTHCHECK -- wait for running state
Wait-ContainerRunning -ContainerName 'harmoni-kafka-ui' -TimeoutSec 60

Write-Ok "All core services ready"

# =============================================================================
# STEP 7 -- Apply SQL migrations in dependency order
#
# Order matters: identity + scoring + orchestrator tables must exist before
# 002_indexes.sql references them. Re-running is safe -- all DDL uses IF NOT EXISTS.
# =============================================================================

Write-Step "Applying SQL migrations"

$pgUser = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'harmoni' }
$pgDb   = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB   } else { 'harmoni' }

$MigrationFiles = @(
    'api\migrations\001_tenants_webhooks.sql',
    'identity\migrations\001_initial_accounts.sql',
    'identity\migrations\002_raw_event_tables.sql',
    'scoring\migrations\001_account_scores.sql',
    'scoring\migrations\002_account_fatigue_scores.sql',
    'orchestrator\migrations\001_nba_actions.sql',
    'api\migrations\002_indexes.sql',
    'api\migrations\003_audit_log.sql'
)

foreach ($relPath in $MigrationFiles) {
    $fullPath = Join-Path $RepoRoot $relPath

    if (-not (Test-Path $fullPath)) {
        Write-Warn "Migration not found, skipping: $relPath"
        continue
    }

    Write-Host "    Applying $relPath ..." -ForegroundColor DarkGray

    $sqlContent = Get-Content -Path $fullPath -Raw
    $sqlContent | docker exec -i harmoni-postgres psql -U $pgUser -d $pgDb -v ON_ERROR_STOP=1

    if ($LASTEXITCODE -ne 0) {
        Exit-Script "Migration failed on $relPath (exit code $LASTEXITCODE)"
    }
}

Write-Ok "$($MigrationFiles.Count) migration file(s) applied"

# =============================================================================
# Helper: launch a child PowerShell window via -EncodedCommand
#
# -EncodedCommand accepts a Base64-encoded UTF-16LE command string, which
# avoids all argument-parsing issues when the repo path contains spaces,
# ampersands, or other shell-special characters.
# =============================================================================

function Start-EncodedWindow {
    param(
        [Parameter(Mandatory)][string]$Title,
        [Parameter(Mandatory)][string]$Command,
        [string]$WorkDir = $RepoRoot
    )

    $fullCmd = '$Host.UI.RawUI.WindowTitle = ''' + $Title + '''; ' + $Command
    $bytes   = [System.Text.Encoding]::Unicode.GetBytes($fullCmd)
    $encoded = [Convert]::ToBase64String($bytes)

    Start-Process powershell.exe `
        -ArgumentList "-NoExit", "-EncodedCommand", $encoded `
        -WorkingDirectory $WorkDir
}

# =============================================================================
# STEP 8 -- FastAPI server (port 8000)
# =============================================================================

Write-Step "Opening FastAPI server window  (port 8000)"

$apiCommand = '$env:PYTHONPATH = ''' + $RepoRoot + '''; ' +
              'Set-Location ''' + $RepoRoot + '''; ' +
              '& ''' + $pythonExe + ''' -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000'

Start-EncodedWindow -Title "harmoni API :8000" -Command $apiCommand -WorkDir $RepoRoot

Write-Ok "API server window opened  ->  http://localhost:8000"

# =============================================================================
# STEP 9 -- Next.js dashboard dev server (port 3000)
# =============================================================================

Write-Step "Opening Next.js dashboard window  (port 3000)"

$DashDir  = Join-Path $RepoRoot 'dashboard'
$NextBin  = Join-Path $DashDir 'node_modules\next\dist\bin\next'

# Install npm dependencies if node_modules is missing
if (-not (Test-Path $NextBin)) {
    Write-Warn "node_modules not found -- running npm install in dashboard\"
    $origDir = (Get-Location).Path
    Set-Location $DashDir
    npm install
    if ($LASTEXITCODE -ne 0) { Exit-Script "npm install failed" }
    Set-Location $origDir
}

# Verify node is available
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Exit-Script "node not found on PATH. Install Node.js 20+ and retry."
}
$nodeExe = $nodeCmd.Source

# Invoke the Next.js binary directly with node to bypass cmd.exe path parsing
$feCommand = 'Set-Location ''' + $DashDir + '''; ' +
             '& ''' + $nodeExe + ''' ''' + $NextBin + ''' dev'

Start-EncodedWindow -Title "harmoni Dashboard :3000" -Command $feCommand -WorkDir $DashDir

Write-Ok "Next.js dev server window opened  ->  http://localhost:3000"

# =============================================================================
# STEP 10 -- Wait for API then open browser
# =============================================================================

Write-Step "Waiting for API server to be ready ..."

$apiReady = $false
for ($i = 1; $i -le 30; $i++) {
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" `
                               -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $apiReady = $true; break }
    } catch { }
    Write-Host "    API not yet up -- ${i}/30 ..." -ForegroundColor DarkGray
    Start-Sleep 2
}

if ($apiReady) {
    Write-Ok "API is responding"
} else {
    Write-Warn "API did not respond after 60s -- opening browser anyway"
}

Start-Process "http://localhost:3000"
Write-Ok "Browser opened at http://localhost:3000"

# =============================================================================
# STEP 11 -- Summary
# =============================================================================

$div = "  " + ("-" * 54)

Write-Host ""
Write-Host $div                                                             -ForegroundColor DarkGray
Write-Host "  Service                  URL"                                 -ForegroundColor White
Write-Host $div                                                             -ForegroundColor DarkGray
Write-Host "  Dashboard (Next.js)      http://localhost:3000"               -ForegroundColor Green
Write-Host "  API (FastAPI)            http://localhost:8000"               -ForegroundColor Green
Write-Host "  API docs (Swagger)       http://localhost:8000/docs"          -ForegroundColor Green
Write-Host "  API docs (ReDoc)         http://localhost:8000/redoc"         -ForegroundColor Green
Write-Host $div                                                             -ForegroundColor DarkGray
Write-Host "  PostgreSQL               localhost:5432"                      -ForegroundColor Cyan
Write-Host "  Redis                    localhost:6379"                      -ForegroundColor Cyan
Write-Host "  ClickHouse               http://localhost:8123"               -ForegroundColor Cyan
Write-Host "  Kafka                    localhost:9092"                      -ForegroundColor DarkGray
Write-Host "  Schema Registry          http://localhost:8081"               -ForegroundColor DarkGray
Write-Host "  Kafka UI                 http://localhost:8080"               -ForegroundColor DarkGray
Write-Host "  Airflow                  http://localhost:8082  (admin/admin)" -ForegroundColor DarkGray
Write-Host $div                                                             -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Demo mode (no API needed):  click 'Try live demo' on the login page"  -ForegroundColor Gray
Write-Host "  Stop Docker services:       docker compose down"              -ForegroundColor Gray
Write-Host "  Remove volumes too:         docker compose down -v"           -ForegroundColor Gray
Write-Host ""
