# Policy Generator — install & lab setup

*App 1.1.x · targets Pentaho Data Catalog 11.0.0 (public API v3)*

**Primary role:** Data Steward / Data Developer / IT Administrator
**Estimated time:** 15–20 minutes (app only — the shared lab is a separate, one-time build)

---

## Overview

This guide stands up the **Policy Generator** — the app that reads the
Glossary Generator's **Classification Registry** and authors PDC's Data
Identification methods (Data Patterns + Dictionaries) from it. The app is
**local-first, deterministic and offline**: no LLM, no database, no network
calls in the author stage. All it needs is Python and a Registry file.

### What you will have at the end

- The web UI running at `http://127.0.0.1:5001` (the Glossary Generator keeps
  port 5000 — both run side by side).
- The CLI (`python -m policy_generator`) working with zero dependencies.
- The offline selftest passing (20 checks, no PDC, no network).
- A Registry loaded and a method set authored, ready for
  **Management → Data Identification → Import** in PDC.

## Prerequisites

| What | Why | Where it comes from |
| --- | --- | --- |
| **Python 3.9+** on the host | runs the app (the launchers check this) | python.org — on Windows tick *Add to PATH* |
| **The shared lab + a scenario** (e.g. CSCU) | the data estate PDC scans and identifies | the Glossary repo's guide: `PDC-Glossary-Generator/data_sources/lab/lab-setup.docx` (Parts A–I) — the one-time build of the PDC VM, network, lab stack and scenario load |
| **A Classification Registry** | the only input the author stage needs | written by the Glossary Generator at Generate time: `glossary_generator/registries/registry.<glossary-uuid>.json` |
| **PDC 11.0.0 reachable over HTTPS** | to import the methods and run Data Identification | the lab VM (e.g. `https://pentaho.io` on `192.168.1.200`) |
| A PDC user allowed to import under **Management → Data Identification** | the import step | Workshop 0 (Preflight) of the scenario's courseware |

**No LLM, no Ollama, no GPU** — the evidence this app authors from (induced
regexes, profiled value lists) was already gathered by the Glossary app's
scan and travels inside the Registry.

## Part A — Get the repository

```sh
git clone https://github.com/jporeilly/PDC-Policy.git
cd PDC-Policy
```

### Cloning into the lab VM's `PDC-Demo` folder

On the lab VM, `~/PDC-Demo` is the **Glossary repo's checkout** — it already
holds `data_sources/` (the lab + scenario scripts) and `glossary_generator/`
(the app). This repo is self-contained, so you can clone it **inside** that
folder and keep the whole lab in one place; git treats a nested repo as a
single untracked directory, the two never interfere:

```sh
cd ~/PDC-Demo
git clone https://github.com/jporeilly/PDC-Policy.git
echo "PDC-Policy/" >> .git/info/exclude   # keep the Glossary repo's `git status` clean
cd PDC-Policy/policy_generator
bash run.sh --host 0.0.0.0        # VM checkouts may lack exec bits — bash, not ./
```

`--host 0.0.0.0` binds all interfaces so the UI is reachable from the
Windows host at `http://192.168.1.200:5001`. Cloned here, the app also
**finds the Registry by itself**: it probes the parent folder for
`glossary_generator/registries/registry.*.json` (and sibling Glossary
checkouts), lists what it finds newest-first on the Load card, and loads it
in one click — a single match loads automatically. The CLI does the same
when you omit the path (`python -m policy_generator info`). To point
somewhere else entirely, set `POLICY_REGISTRY_DIR`.

(Prefer it fully separate? Cloning to `~/PDC-Policy` beside `~/PDC-Demo`
works identically — nothing in the app assumes a location.)

### Where things live in the repository

| Path | What it is |
| --- | --- |
| `policy_generator/` | the app: engine (`registry.py`, `author.py`), CLI, web UI (`app.py` + `templates/`), launchers, `VERSION` |
| `docs/CONTRACT.md` | the `classification-registry/1` schema, field by field |
| `docs/CHANGELOG.md` | version history (the app version lives in `policy_generator/VERSION`) |
| `courseware/CSCU/` | the CSCU workshop set for this app (+ the Word-guide builder in `tools/`) |
| `docs/INSTALL.md` | this guide — the markdown master `docs/lab-setup.docx` is generated from |

## Part B — Run the web UI

The launcher creates a local virtualenv (`.venv`), installs the (Flask-only)
dependencies — re-installing only when `requirements.txt` changes — and
starts the app. Nothing touches your system Python.

**Linux / macOS:**

```sh
cd policy_generator
./run.sh                 # → http://127.0.0.1:5001
```

**Windows (PowerShell):**

```powershell
cd policy_generator
.\run.ps1                # or double-click run.bat
```

Options work the same as the Glossary app's launcher: `--port 8081` /
`-Port 8081` to change the port, `--host 0.0.0.0` / `-BindHost 0.0.0.0` to
bind all interfaces on a lab VM, `HOST`/`PORT` environment variables.

Open `http://127.0.0.1:5001` and confirm the banner shows the app version.

`[SCREENSHOT: the Policy Generator UI freshly loaded — banner, stage pills, the three cards]`

## Part C — The CLI (no dependencies at all)

The engine also runs straight from a repo checkout — useful on machines
where you don't want a venv or a browser:

```sh
python -m policy_generator --version
python -m policy_generator info   path/to/registry.<uuid>.json
python -m policy_generator author path/to/registry.<uuid>.json -o out/ --prefix CSCU
```

## Part D — Verify the install

```sh
python -m policy_generator.selftest
```

**Success looks like this:** `20 passed, 0 failed` — the selftest builds a
fixture Registry in memory and exercises the whole author pipeline offline.

Then load a real Registry in the UI (drag-drop, or paste its path) and check
the contract summary: concepts, seeds, resolved term ids, governed tags. The
expandable **"What the summary numbers mean"** panel on the page explains
each number and what to do when it looks wrong.

## Part E — Keeping the app up to date

```sh
git pull
```

Restart the launcher afterwards — it detects a changed `requirements.txt`
and re-installs only then. Your `.venv` and any authored `out/` directories
are git-ignored and survive updates.

## Part F — The PDC side (when you're ready to import)

The authored zip is shaped for PDC's UI import — the full walkthrough with
checkpoints is the CSCU workshop
(`courseware/CSCU/Workshop-Policy-Generator-CSCU.md`). In short:

1. **Management → Data Identification → Patterns → Import** — the files
   under `Patterns/`.
2. **Management → Data Identification → Dictionaries → Import** — each
   `*_rule.json` **with** its values CSV.
3. Run **Data Identification** on the scenario's sources (and **Scan Files**
   on the object store).
4. Verify the governed tags landed — and only governed tags.

The **reconcile / deploy / drift-check** stages will automate the PDC side
over the public API (v3); they need API credentials, which the author stage
never does.

## Part G — Troubleshooting

| Symptom | Cause & fix |
| --- | --- |
| `run.ps1` won't start: *running scripts is disabled* | PowerShell execution policy — use `run.bat` (it bypasses for that one process), or `powershell -ExecutionPolicy Bypass -File .\run.ps1` |
| Port 5001 busy | another app owns it — `./run.sh --port 8081` / `.\run.ps1 -Port 8081` |
| `pip install` fails on a brand-new Python | no prebuilt wheels yet — `.\run.ps1 -PyVersion 3.12` forces a known-good interpreter |
| `run.sh: bad interpreter` or `^M` errors on the VM | the checkout converted line endings — the repo pins `*.sh` to LF (`.gitattributes`), so re-clone; a VM checkout may also lack exec bits: run `bash run.sh` |
| UI loads but *Load path* can't find the Registry | the path is resolved on the machine the app runs on — when the app and the Glossary checkout are on different hosts, use drag-drop upload instead |
| `info` shows `resolved term ids: 0` | normal before glossary import — import the glossary in PDC, run the Glossary app's **Resolve term ids**, re-export; until then rules bind terms by name |
| Import rejected by PDC | dictionaries must be imported **with** their values CSV; patterns and dictionaries import on their own separate pages |

---

*The shared lab (PDC VM, network, demo Postgres on 5433 + MinIO, scenario
loads) is owned by the Glossary repo — its `lab-setup.docx` Parts A–I is the
authoritative build guide, including rebuild troubleshooting (G1–G4). All
scenario data is fictional and generated for training.*
