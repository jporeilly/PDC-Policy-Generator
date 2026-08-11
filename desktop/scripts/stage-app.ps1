<#
.SYNOPSIS
    Stage the Python app + built React UI for bundling.

.DESCRIPTION
    Copies the policy_generator package and frontend\dist into
    src-tauri\vendor\app, which tauri.conf.json's bundle.resources maps to
    "app" inside the install.

    The staged tree MIRRORS the repo layout:

        app\boot.py                     (desktop launcher - see desktop\boot.py)
        app\policy_generator\api.py
        app\frontend\dist\index.html
        app\CHANGELOG.md                (served by /changelog)

    That is not cosmetic. api.py resolves the built UI as
    REPO_ROOT/frontend/dist - one level up from the package - so flattening
    the two into a single directory would leave the server running with no UI
    to serve.

    This app keeps NO local state beside the code (its one write lands beside
    the loaded Registry, and PDC credentials live in memory), so there is no
    state-file exclude list - just build debris.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
# Without this an undefined variable expands to empty and robocopy just returns
# exit 16 - which is how the staging destination silently became "" once.
Set-StrictMode -Version Latest

$desktopDir = Split-Path -Parent $PSScriptRoot
$repoRoot   = Split-Path -Parent $desktopDir
$srcApp     = Join-Path $repoRoot "policy_generator"
$srcUi      = Join-Path $repoRoot "frontend\dist"
$stageDir   = Join-Path $desktopDir "src-tauri\vendor\app"
$stageApp   = Join-Path $stageDir "policy_generator"
$stageUi    = Join-Path $stageDir "frontend\dist"

function Ok($m)   { Write-Host "  [ok] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "  [!]  $m" -ForegroundColor Yellow }

Write-Host ""
Write-Host "  Staging the app" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath (Join-Path $srcApp "api.py"))) {
    throw "policy_generator\api.py not found - is $repoRoot the repo root?"
}
if (-not (Test-Path -LiteralPath (Join-Path $srcUi "index.html"))) {
    throw "frontend\dist\index.html not found - run 'npm run build' in frontend\ first"
}

if (Test-Path -LiteralPath $stageDir) { Remove-Item -LiteralPath $stageDir -Recurse -Force }
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null

# robocopy: mirror of a clean tree. Exit codes 0-7 are success (8+ is a real
# failure) - a quirk worth pinning, because treating any non-zero as failure
# makes every build look broken.
#
# /XD is RELATIVE on purpose: an absolute path matches only the top-level
# directory, so any subpackage __pycache__ from the dev checkout would ship
# into Program Files, where the uninstaller leaves it behind (found on
# PDC-Insights 1.17.0). A relative name matches at any depth.
#
# .venv matters here specifically: run.ps1 creates the dev virtualenv INSIDE
# policy_generator\, so without the exclude every release since 1.10.0 shipped
# a second Python's packages (~17 MB: pip, activate scripts, venv copies of
# fastapi/uvicorn) into Program Files beside the vendored runtime.
& robocopy $srcApp $stageApp "/E" "/NFL" "/NDL" "/NJH" "/NJS" "/NP" `
    "/XD" "__pycache__" ".pytest_cache" ".venv" "venv" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging the app package (exit $LASTEXITCODE)" }

# The built SPA, one level up from policy_generator - the shape api.py expects
# (see the .DESCRIPTION note above).
New-Item -ItemType Directory -Path $stageUi -Force | Out-Null
& robocopy $srcUi $stageUi "/E" "/NFL" "/NDL" "/NJH" "/NJS" "/NP" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy failed staging the UI (exit $LASTEXITCODE)" }

# /changelog serves REPO_ROOT\CHANGELOG.md; without it the endpoint answers
# "No changelog available." - not broken, just poorer.
Copy-Item -LiteralPath (Join-Path $repoRoot "CHANGELOG.md") -Destination (Join-Path $stageDir "CHANGELOG.md") -Force

# boot.py puts the app root on sys.path before importing it. The embeddable
# runtime's ._pth replaces sys.path outright, so without this the server cannot
# import policy_generator.api whatever working directory it is given.
Copy-Item -LiteralPath (Join-Path $desktopDir "boot.py") -Destination (Join-Path $stageDir "boot.py") -Force

# Belt and braces: prove no environment slipped through. The staged tree runs
# on the VENDORED runtime; a bundled dev venv is 17 MB of wrong Python.
if (Test-Path -LiteralPath (Join-Path $stageApp ".venv")) {
    throw "the dev .venv reached the staging tree - fix the exclude list"
}

# The paths the shell and the server actually depend on. Assert them here,
# where the fix is obvious, rather than at first launch on a customer's laptop.
foreach ($must in @((Join-Path $stageApp "api.py"),
                    (Join-Path $stageApp "VERSION"),
                    (Join-Path $stageUi  "index.html"),
                    (Join-Path $stageDir "boot.py"),
                    (Join-Path $stageDir "CHANGELOG.md"))) {
    if (-not (Test-Path -LiteralPath $must)) { throw "staging incomplete: $must is missing" }
}

# Prove the staged tree can actually be imported, using the runtime that will
# ship with it. File-existence checks cannot catch a module excluded by mistake;
# this can, and it costs a couple of seconds.
$vendorPy = Join-Path $desktopDir "src-tauri\vendor\python\python.exe"
if (Test-Path -LiteralPath $vendorPy) {
    $probe = "import sys; sys.path.insert(0, sys.argv[1]); import policy_generator.api; print('import ok')"
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    # -B: do NOT write bytecode. Without it this check compiles __pycache__ into
    # the tree robocopy just finished excluding it from, and those .pyc files
    # then ship - stale caches for a Python version the user may not even be
    # running. The check has to leave the stage exactly as it found it.
    $out = & $vendorPy -B -c $probe $stageDir 2>&1
    $code = $LASTEXITCODE
    $ErrorActionPreference = $prevEap
    if ($code -ne 0) {
        $out | ForEach-Object { Warn $_ }
        throw "the staged tree cannot import policy_generator.api - a module is missing from the stage"
    }
    # Belt and braces: -B covers this run, but anything else that touches the
    # stage would leave caches behind, and a shipped .pyc is invisible until
    # someone lists the installer.
    Get-ChildItem -LiteralPath $stageDir -Recurse -Directory -Filter "__pycache__" |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }

    Ok "staged tree imports cleanly"
} else {
    Warn "no vendored runtime yet - skipping the import check (run fetch:python first)"
}

$count = (Get-ChildItem -LiteralPath $stageDir -Recurse -File).Count
Ok "staged $count file(s) to src-tauri\vendor\app"
Write-Host ""

# robocopy returns 1 for "files were copied" and PowerShell surfaces the LAST
# native exit code as the script's, so a successful run would look like a
# failure to npm and abort the tauri build.
exit 0
