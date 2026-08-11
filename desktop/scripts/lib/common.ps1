<#
    Shared helpers for the desktop scripts.

    Exists because check-environment.ps1 and the staging both have to answer
    the same questions - "which Python do I run", "where is the app", "where
    would a Registry be" - and two copies of those rules is two chances to
    disagree with policy_generator\registry.py, which is the actual authority.

    Dot-source it:  . (Join-Path $PSScriptRoot "lib\common.ps1")

    ASCII-only on purpose (PowerShell 5.1).
#>

function Get-RepoRoot {
    <# The PDC-Policy checkout root, from a script in desktop\scripts. #>
    param([Parameter(Mandatory)][string] $ScriptRoot)
    return (Split-Path -Parent (Split-Path -Parent $ScriptRoot))
}

function Get-DesktopDir {
    param([Parameter(Mandatory)][string] $ScriptRoot)
    return (Split-Path -Parent $ScriptRoot)
}

function Resolve-PyExe {
    <#
        The interpreter to run. Candidates cover BOTH layouts these scripts live
        in, because the installer bundles copies of them:

          installed:  $INSTDIR\provisioning\  ->  $INSTDIR\python\python.exe
          checkout:   desktop\scripts\        ->  desktop\src-tauri\vendor\python\

        Falls back to Python 3.10+ on PATH. Returns $null when there is none.
    #>
    param([Parameter(Mandatory)][string] $ScriptRoot)

    $here = Split-Path -Parent $ScriptRoot     # provisioning\.. or scripts\..
    foreach ($rel in @("python\python.exe", "src-tauri\vendor\python\python.exe")) {
        $c = Join-Path $here $rel
        if (Test-Path -LiteralPath $c) { return $c }
    }
    foreach ($cand in @("python", "py")) {
        try {
            & $cand -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 10) else 1)" 2>$null
            if ($LASTEXITCODE -eq 0) { return $cand }
        } catch {}
    }
    return $null
}

function Resolve-AppRoot {
    <#
        The app root: the directory holding the policy_generator package.

        Probed on policy_generator\api.py, the one file whose position is
        fixed - boot.py runs it by name.

        CHECKOUT FIRST among the dev candidates: vendor\app is a build artifact
        that goes stale the moment the source changes, and on a dev machine both
        exist. In an installed layout only $INSTDIR\app is present, so it wins
        there by being the only one.
    #>
    param([Parameter(Mandatory)][string] $ScriptRoot)

    $here = Split-Path -Parent $ScriptRoot
    $candidates = @(
        (Join-Path $here "app"),                          # installed
        (Get-RepoRoot $ScriptRoot),                       # checkout
        (Join-Path $here "src-tauri\vendor\app")          # staged
    )
    foreach ($c in $candidates) {
        if (Test-Path -LiteralPath (Join-Path $c "policy_generator\api.py")) { return $c }
    }
    return $null
}

function Get-RegistryDirs {
    <#
        Where a Classification Registry could be waiting, mirroring
        policy_generator\registry.py's discover_registries() candidates that
        exist on a LAPTOP install: the packaged Glossary app's per-user state
        (Tauri-keyed, then the app's own fallback), then POLICY_REGISTRY_DIR.
        Returns only directories that exist - ALWAYS as an array. The comma
        matters: function output unrolls through the pipeline, so a bare @()
        reaches the caller as $null when no folder matches and as a bare
        string when one does - and under Set-StrictMode Latest neither has
        .Count, which killed check-environment.ps1 (and made the installer
        print "[!!] problems found") on any machine without a populated
        Glossary hand-off folder.
    #>
    $candidates = @()
    if ($env:POLICY_REGISTRY_DIR) { $candidates += $env:POLICY_REGISTRY_DIR }
    if ($env:APPDATA) {
        $candidates += (Join-Path $env:APPDATA "com.pentaho.pdc-glossary\registries")
        $candidates += (Join-Path $env:APPDATA "PDC-Glossary\registries")
    }
    return ,@($candidates | Where-Object { Test-Path -LiteralPath $_ })
}
