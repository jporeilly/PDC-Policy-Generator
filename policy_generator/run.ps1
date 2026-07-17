<#
  PDC Policy Generator - Windows launcher (PowerShell)

  Windows equivalent of run.sh. Creates a local virtualenv (.venv), installs
  dependencies (re-installing only when requirements.txt changes), then launches
  the app with `uvicorn policy_generator.api:app`. Nothing touches your system Python.

    .\run.ps1                    # http://127.0.0.1:5001
    .\run.ps1 -Port 8081         # choose a port
    .\run.ps1 -PyVersion 3.12    # force a Python (avoids no-wheel-yet versions)
    .\run.ps1 -BindHost 0.0.0.0  # bind all interfaces (e.g. on a lab VM)
    $env:PORT=8081; .\run.ps1    # env vars work too (HOST, PORT)

  The default port is 5001 so the Glossary Generator (5000) can run alongside.

  First run only, if scripts are blocked:
    powershell -ExecutionPolicy Bypass -File .\run.ps1
  (or use run.bat, which does that for you)
#>
[CmdletBinding()]
param(
    [int]$Port,
    [string]$BindHost,     # NOTE: not -Host; $Host is reserved in PowerShell
    [string]$PyVersion     # force a specific Python, e.g. -PyVersion 3.12
)

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# HOST/PORT: param > existing env > default. uvicorn is launched with these.
if (-not $BindHost) { $BindHost = if ($env:HOST) { $env:HOST } else { '127.0.0.1' } }
if (-not $Port)     { $Port     = if ($env:PORT) { [int]$env:PORT } else { 5001 } }

function Ok   ($m) { Write-Host "  " -NoNewline; Write-Host "OK  " -ForegroundColor Green  -NoNewline; Write-Host $m }
function Warn ($m) { Write-Host "  " -NoNewline; Write-Host "!   " -ForegroundColor Yellow -NoNewline; Write-Host $m }
function Die  ($m) { Write-Host "  X  $m" -ForegroundColor Red; exit 1 }

Write-Host ""
$Ver = ""
try { if (Test-Path (Join-Path $PSScriptRoot "VERSION")) { $Ver = " v" + (Get-Content (Join-Path $PSScriptRoot "VERSION") -Raw).Trim() } } catch {}
Write-Host "  PDC Policy Generator$Ver" -ForegroundColor Cyan
Write-Host "  Registry -> Data Identification.  Author import-ready PDC patterns and" -ForegroundColor DarkGray
Write-Host "  dictionaries from the Glossary Generator's Classification Registry." -ForegroundColor DarkGray
Write-Host ""

# --- pre-flight ------------------------------------------------------------
Write-Host "  Pre-flight"

# Find a Python. Prefer known-good 3.13/3.12/3.11 over whatever 'py -3'
# resolves to (the *newest*, which may have no wheels yet). -PyVersion forces one.
function Probe-Py($cand) {
    # returns the version string if $cand runs and is >= 3.9, else $null
    try {
        $v = & ([scriptblock]::Create("$cand -c `"import sys;print('.'.join(map(str,sys.version_info[:3]))) if sys.version_info[:2]>=(3,9) else sys.exit(1)`"")) 2>$null
        if ($LASTEXITCODE -eq 0 -and $v) { return $v.Trim() }
    } catch {}
    return $null
}

if ($PyVersion) {
    $candidates = @("py -$PyVersion")
} else {
    $candidates = @('py -3.13', 'py -3.12', 'py -3.11', 'py -3', 'python', 'python3')
}

$py = $null; $pyver = $null
foreach ($cand in $candidates) {
    $exe = ($cand -split ' ')[0]
    if (-not (Get-Command $exe -ErrorAction SilentlyContinue)) { continue }
    $v = Probe-Py $cand
    if ($v) { $py = $cand; $pyver = $v; break }
}
if (-not $py) {
    if ($PyVersion) { Die "Python $PyVersion not found. Check 'py --list', or install it from python.org." }
    Die "Python 3.9+ not found on PATH. Install 3.12 from python.org (tick 'Add to PATH')."
}
Ok "Python $pyver ($py)"

if (-not (Test-Path requirements.txt)) { Die "requirements.txt not found - run this from the app folder." }
if (-not (Test-Path api.py))           { Die "api.py not found - run this from the app folder." }
Ok "App files present"

# Port availability (best-effort)
try {
    $bindIp = if ($BindHost -eq '0.0.0.0') { [System.Net.IPAddress]::Any } else { [System.Net.IPAddress]::Parse($BindHost) }
    $listener = [System.Net.Sockets.TcpListener]::new($bindIp, $Port)
    $listener.Start(); $listener.Stop()
    Ok "Port $Port is free on $BindHost"
} catch {
    Warn "Port $Port looks busy on $BindHost - start with '-Port <n>' if launch fails"
}
Write-Host ""

# --- virtualenv + dependencies (reinstall only when requirements change) ---
Write-Host "  Environment"
$venvPy   = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$pyStamp  = '.venv\.pyver'
$havePyv  = if (Test-Path $pyStamp) { (Get-Content $pyStamp -Raw).Trim() } else { '' }
# Rebuild if there's no venv, its python is missing, or it was built by a
# different interpreter version (e.g. an old attempt with no wheels).
if ((-not (Test-Path $venvPy)) -or ($havePyv -ne $pyver)) {
    if (Test-Path .venv) {
        $wasPyv = if ($havePyv) { $havePyv } else { 'incomplete' }
        Warn "Rebuilding .venv (was $wasPyv, now $pyver)"
        Remove-Item -Recurse -Force .venv
    }
    Write-Host "  creating virtualenv (.venv) on $pyver..." -ForegroundColor DarkGray
    & ([scriptblock]::Create("$py -m venv .venv"))
    if ($LASTEXITCODE -ne 0) { Die "Failed to create virtualenv." }
    Set-Content -LiteralPath $pyStamp -Value $pyver -NoNewline
}
if (-not (Test-Path $venvPy)) { Die "venv python not found at $venvPy" }

$stamp   = '.venv\.req-stamp'
$reqHash = (Get-FileHash requirements.txt -Algorithm SHA1).Hash
$have    = if (Test-Path $stamp) { Get-Content $stamp -Raw } else { '' }
if ($have.Trim() -ne $reqHash) {
    Write-Host "  installing dependencies..." -ForegroundColor DarkGray
    & $venvPy -m pip install -q --upgrade pip | Out-Null
    & $venvPy -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Die "pip install failed. Usually a missing prebuilt wheel for Python $pyver - re-run with an older Python, e.g.  .\run.ps1 -PyVersion 3.12"
    }
    Set-Content -LiteralPath $stamp -Value $reqHash -NoNewline
    Ok "Dependencies installed"
} else {
    Ok "Dependencies up to date"
}
Write-Host ""

# --- launch ----------------------------------------------------------------
$env:HOST = $BindHost
$env:PORT = "$Port"
# resolve the app dir through a junction/symlink (the PDC-Demo layout links
# policy_generator/ flat) so the dist check looks in the real repo root,
# the same way api.py resolves __file__
$appItem = Get-Item $PSScriptRoot -Force
$realAppDir = if ($appItem.LinkType -and $appItem.Target) { [string]$appItem.Target } else { $PSScriptRoot }
$uiDist = Join-Path (Split-Path $realAppDir -Parent) 'frontend\dist'
if (-not (Test-Path $uiDist)) {
    Warn "React UI not built (frontend\dist missing) - API + /docs only. Build with: cd ..\frontend; npm install; npm run build"
}
Write-Host "  Ready"
Write-Host "  -> http://${BindHost}:${Port}" -ForegroundColor Cyan -NoNewline
Write-Host "   (UI | /docs for the API | Ctrl-C to stop)" -ForegroundColor DarkGray
Write-Host ""
Set-Location ..
& $venvPy -m uvicorn policy_generator.api:app --host $BindHost --port $Port
