<#
.SYNOPSIS
    Post-install environment check: what is missing, and how to fix it.

.DESCRIPTION
    Reports rather than blocks. Only WebView2 and a usable Python are FAIL,
    because without them the window does not open. No Registry found is a WARN
    (the app's Load page also accepts a file by hand), and PDC unreachable is a
    WARN (the author stage is fully offline; only reconcile/deploy need a
    server). Treating those as hard failures would teach people to ignore the
    output.

    Runs from BOTH layouts: an installed $INSTDIR\provisioning\ and a checkout
    desktop\scripts\. The shared resolvers in lib\common.ps1 understand both.

.PARAMETER PdcUrl
    PDC base URL to probe. Defaults to PDC_BASE_URL in the environment, then
    asks - unless -NoPrompt or -Json.

.PARAMETER NoPrompt
    Never ask questions. For provisioning runs (the installer uses this).

.PARAMETER Json
    Emit machine-readable results and nothing else on stdout.

.NOTES
    Windows PowerShell 5.1+. ASCII-only on purpose.
#>
[CmdletBinding()]
param(
    [string]$PdcUrl,
    [switch]$NoPrompt,
    [switch]$Json
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$script:Checks   = @()
$script:Failures = 0
$script:Warnings = 0
$script:Fixes    = @()

function Say {
    param([string]$Text = "", [string]$Colour = "Gray")
    if (-not $Json) { Write-Host $Text -ForegroundColor $Colour }
}

function Report {
    param(
        [string]$Name,
        [ValidateSet("OK", "FAIL", "WARN", "SKIP")][string]$State,
        [string]$Detail = "",
        [string]$Fix = ""
    )
    $script:Checks += [ordered]@{ name = $Name; state = $State; detail = $Detail; fix = $Fix }
    if (-not $Json) {
        $colour = @{ OK = "Green"; FAIL = "Red"; WARN = "Yellow"; SKIP = "DarkGray" }[$State]
        Write-Host ("  [{0,-4}] " -f $State) -ForegroundColor $colour -NoNewline
        Write-Host ("{0,-30}" -f $Name) -NoNewline
        Write-Host $Detail -ForegroundColor DarkGray
    }
    if ($State -eq "FAIL") {
        $script:Failures++
        if ($Fix) { $script:Fixes += "  # $Name`n  $Fix" }
    } elseif ($State -eq "WARN") {
        $script:Warnings++
        if ($Fix) { $script:Fixes += "  # $Name (optional)`n  $Fix" }
    }
}

. (Join-Path $PSScriptRoot "lib\common.ps1")

Say ""
Say "  PDC Policy Generator - environment check" "Cyan"
Say "  Reports what is missing and how to fix it. Only WebView2 and Python are" "DarkGray"
Say "  hard requirements; everything else is optional and says so." "DarkGray"
Say ""

# -- the two things that stop the window opening ----------------------------
Say "  Required" "Cyan"

$wv2Keys = @(
    "HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKLM:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    "HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
)
$wv2 = $null
foreach ($k in $wv2Keys) {
    if (Test-Path $k) {
        try {
            $v = (Get-ItemProperty -Path $k -ErrorAction Stop).pv
            if ($v) { $wv2 = $v; break }
        } catch {}
    }
}
if ($wv2) {
    Report "WebView2 runtime" "OK" $wv2
} else {
    Report "WebView2 runtime" "FAIL" "not found - the app window cannot render" `
        "winget install -e --id Microsoft.EdgeWebView2Runtime"
}

$script:PyExe = Resolve-PyExe $PSScriptRoot
$bundled = $script:PyExe -and (Test-Path -LiteralPath $script:PyExe) -and
           ($script:PyExe -like "*\python\python.exe")

if (-not $script:PyExe) {
    Report "Python 3.10+" "FAIL" "no interpreter found, bundled or on PATH" `
        "reinstall the app, or install Python: winget install -e --id Python.Python.3.12"
} else {
    $ver = & $script:PyExe -c "import sys;print('.'.join(map(str,sys.version_info[:3])))" 2>$null
    if ($bundled) {
        Report "Python (bundled)" "OK" ("" + $ver + " - shipped with the app, nothing to install")
    } else {
        Report "Python 3.10+" "OK" ("" + $ver + " - from PATH (running from a checkout)")
    }

    # The imports that actually break in a packaged build. Confirming that
    # python.exe merely EXISTS would miss the failure this check exists for.
    $probe = & $script:PyExe -c "import uvicorn,fastapi,multipart;print('ok')" 2>&1
    if ($LASTEXITCODE -eq 0) {
        Report "Python dependencies" "OK" "uvicorn, fastapi, python-multipart"
    } elseif ($bundled) {
        Report "Python dependencies" "FAIL" "the bundled runtime cannot import its own packages" `
            "the install is incomplete - reinstall"
    } else {
        Report "Python dependencies" "WARN" "not importable from this interpreter" `
            "run.ps1 builds a venv with them; this only matters for a checkout"
    }
}

# -- the Registry hand-off ----------------------------------------------------
Say ""
Say "  Classification Registry (the Glossary Generator's export)" "Cyan"

$regDirs = Get-RegistryDirs
$regFiles = @()
foreach ($d in $regDirs) {
    $regFiles += @(Get-ChildItem -LiteralPath $d -Filter "registry.*.json" -ErrorAction SilentlyContinue)
}
if ($regFiles.Count -gt 0) {
    $newest = $regFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    Report "Registry files" "OK" ("" + $regFiles.Count + " found; newest " + $newest.Name + " (" + $newest.DirectoryName + ")")
} elseif ($regDirs.Count -gt 0) {
    Report "Registry files" "WARN" ("hand-off folder present but empty: " + ($regDirs -join "; ")) `
        "export a Registry from the Glossary Generator, or load a registry.*.json by hand on the Load page"
} else {
    Report "Registry files" "WARN" "no Glossary hand-off folder on this machine" `
        "install the PDC Glossary Generator and export a Registry, or load a registry.*.json by hand on the Load page"
}

# -- PDC ---------------------------------------------------------------------
Say ""
Say "  Pentaho Data Catalog (only reconcile/deploy/drift need it)" "Cyan"

$pdcWhy = $null
if ($PdcUrl) { $pdcWhy = "-PdcUrl" }
if (-not $PdcUrl -and $env:PDC_BASE_URL) {
    $PdcUrl = $env:PDC_BASE_URL
    $pdcWhy = "PDC_BASE_URL"
}
if (-not $PdcUrl -and -not $Json -and -not $NoPrompt -and [Environment]::UserInteractive) {
    Say ""
    Say "  No PDC server is configured. The author stage is fully offline;" "DarkGray"
    Say "  enter one to check reachability now, or press Enter to skip." "DarkGray"
    $answer = Read-Host "  PDC base URL (e.g. https://catalog.example.com)"
    if ($answer) {
        $PdcUrl = $answer.Trim()
        $pdcWhy = "entered now - not saved; the app asks on its Reconcile page"
    }
}

if (-not $PdcUrl) {
    Report "PDC" "SKIP" "not configured - authoring works fully offline; the app asks when you reconcile"
} else {

# PDC routes by vhost. A bare IP answers 401 on every path, which looks like bad
# credentials and sends people to reset passwords that were never wrong.
if ($PdcUrl -match '^https?://(\d{1,3}\.){3}\d{1,3}(:\d+)?/?$') {
    Report "PDC URL" "WARN" "$PdcUrl is a bare IP - PDC routes by vhost and will answer 401 everywhere" `
        "use the server's hostname instead of its IP address"
} else {
    Report "PDC URL" "OK" ("$PdcUrl (from $pdcWhy)")
}

function Test-Pdc([string]$Url) {
    try {
        $r = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return @{ Reached = $true; Detail = "HTTP " + $r.StatusCode; Tls = $true }
    } catch {
        $resp = $null
        try { $resp = $_.Exception.Response } catch {}
        if ($resp) {
            return @{ Reached = $true
                      Detail  = "HTTP " + [int]$resp.StatusCode + " - up, credentials are entered in the app"
                      Tls     = $true }
        }
        return @{ Reached = $false; Detail = $_.Exception.Message; Tls = $true }
    }
}

$pdc = Test-Pdc $PdcUrl

# A self-signed certificate is NOT unreachability. Retry with validation off
# purely to tell the two apart - different problems, different fixes.
if (-not $pdc.Reached -and $pdc.Detail -match 'trust relationship|SSL|TLS|certificate') {
    $saved = [System.Net.ServicePointManager]::CertificatePolicy
    try {
        Add-Type -TypeDefinition @'
using System.Net;
using System.Security.Cryptography.X509Certificates;
public class PdcCheckCertPolicy : ICertificatePolicy {
    public bool CheckValidationResult(ServicePoint sp, X509Certificate c, WebRequest r, int p) { return true; }
}
'@ -ErrorAction SilentlyContinue
        [System.Net.ServicePointManager]::CertificatePolicy = New-Object PdcCheckCertPolicy
        $retry = Test-Pdc $PdcUrl
        if ($retry.Reached) { $pdc = @{ Reached = $true; Detail = $retry.Detail; Tls = $false } }
    } finally {
        [System.Net.ServicePointManager]::CertificatePolicy = $saved
    }
}

if ($pdc.Reached -and $pdc.Tls) {
    Report "PDC reachable" "OK" $pdc.Detail
} elseif ($pdc.Reached) {
    Report "PDC reachable" "WARN" ($pdc.Detail + " - certificate is not trusted (self-signed)") `
        "expected on a lab VM; the app's connect dialog can skip TLS verification"
} else {
    Report "PDC reachable" "WARN" "$PdcUrl - $($pdc.Detail)" `
        "check the hostname and that the server is up; authoring works without PDC"
}

}   # end: a PDC server was configured

# -- summary -----------------------------------------------------------------
if ($Json) {
    [ordered]@{
        failures = $script:Failures
        warnings = $script:Warnings
        checks   = $script:Checks
    } | ConvertTo-Json -Depth 5
    exit ([int]($script:Failures -gt 0))
}

Say ""
if ($script:Failures -eq 0 -and $script:Warnings -eq 0) {
    Write-Host "  Everything checks out." -ForegroundColor Green
} elseif ($script:Failures -eq 0) {
    Write-Host ("  Ready to run. " + $script:Warnings + " optional item(s) not configured.") -ForegroundColor Yellow
} else {
    Write-Host ("  " + $script:Failures + " blocking problem(s), " +
                $script:Warnings + " optional.") -ForegroundColor Red
}
if ($script:Fixes.Count -gt 0) {
    Say ""
    Say "  Suggested commands:" "Cyan"
    $script:Fixes | ForEach-Object { Say $_ "DarkGray" }
}
Say ""

exit ([int]($script:Failures -gt 0))
