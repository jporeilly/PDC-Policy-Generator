# Desktop shell

Wraps the Policy Generator into a Windows `.exe` installer, the same way the
Glossary Generator and Catalog Insights are packaged (Tauri + a vendored
Python).

The app itself is unchanged. This is a Tauri window that starts the existing
FastAPI server on a free port and points a webview at it, so the desktop and
browser builds cannot drift apart — there is one UI, served the same way in
both.

## Layout

```
desktop/
  dist/index.html          splash: polls the backend, then navigates to it
  boot.py                  launcher: sys.path fix for the embeddable runtime
  scripts/fetch-python.ps1 vendors a self-contained Python + the requirements
  scripts/stage-app.ps1    copies policy_generator + built SPA into vendor/app
  scripts/check-environment.ps1  post-install check: what is missing, and the fix
  scripts/lib/common.ps1   shared interpreter / registry-folder resolution
  src-tauri/src/main.rs    window, paths, the invoke commands
  src-tauri/src/server.rs  free port, spawn uvicorn, job object
```

## Build

```powershell
cd frontend; npm ci; npm run build     # the SPA must exist first
cd ..\desktop; npm install
npm run dist                           # stage + tauri:build + collect
```

The installer is copied to **`dist\` at the repo root** (one short path;
`npm run collect` prints it with a sha256). Tauri's own output stays in
`src-tauri/target/release/bundle/nsis/` — `npm run tauri:build` alone stops
there.

`npm run tauri:dev` runs against the checkout instead — no staging, no vendored
runtime, `python` from PATH. Edit Python, reload the window, done.

## What is different from the other two shells

**No state directory plumbing.** The app's one write — `seed-request.json` —
lands beside the loaded Registry, and PDC credentials are held in memory for
the session. Nothing ever writes beside the code, so the packaged build needs
no `*_STATE_DIR` redirect. The per-user data folder
(`%APPDATA%\com.pentaho.pdc-policy`) holds only the shell's own
`startup-report.txt`.

**No Ollama step.** The Policy Generator is deterministic by design — no LLM
anywhere in the pipeline — so the installer's Full type is just the app plus
the environment check. The wizard shows the suite licence page like the other
two apps (`LICENSE.txt`, adapted here: the tool WRITES to the catalog on
Deploy, Registry seeds can carry profiled sample values, and §4 records that
the software contains no AI at all).

**The Registry hand-off is automatic.** `discover_registries()` also looks in
the packaged Glossary Generator's per-user state
(`%APPDATA%\com.pentaho.pdc-glossary\registries`), so when both Windows
installers are on one laptop, a Registry exported from the Glossary app
appears on this app's Load page with nothing configured. The splash says how
many Registry files it can see before the app even opens.

## The installer

`nsis/installer.nsi` adds a components page over Tauri's default template.

| Install type | What runs |
| --- | --- |
| **Full** | app, environment check |
| **Minimal (app only)** | app only |

Silent installs: `setup.exe /S /NoCheck`.

Expect SmartScreen on the unsigned build (*More info → Run anyway*), and a
per-machine install to `C:\Program Files\PDC Policy Generator` that always
prompts for elevation. Verify afterwards with:

```powershell
& "$env:ProgramFiles\PDC Policy Generator\provisioning\check-environment.ps1"
```

## Code signing

`scripts/sign.ps1` runs for every bundled binary and **no-ops with a note when
no thumbprint is set**. It accepts `POLICY_SIGN_THUMBPRINT` or the suite-wide
`PDCG_SIGN_THUMBPRINT`, so one variable signs every PDC-Demo build on this
machine. The repo holds no certificate and no `.pfx`.

## Not done yet

- **Icons are placeholders** (`src-tauri/icons/`) — the suite's generated
  Pentaho mark, not a per-app design.
