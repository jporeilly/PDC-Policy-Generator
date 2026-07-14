# Pentaho Data Catalog Policy Generator

**Version:** 1.1.2 (`policy_generator/VERSION`) · validated against Pentaho Data Catalog 11.0.0 (public API v3) · [changelog](docs/CHANGELOG.md)

A local-first app that **reads the Glossary Generator's Classification
Registry and manages PDC's Data Identification side of the contract**: it
authors import-ready Data Patterns and Dictionaries from the scan's evidence,
each stamping governed tags and binding the governed business term — so what
PDC *identifies* can never quietly diverge from what the glossary *governs*.

It is the second half of a two-app governance pipeline, and it is
**deterministic and offline — no LLM, no database, no network** in the author
stage: every regex and reference list it emits was induced from profiled data
by the [Glossary Generator](https://github.com/jporeilly/PDC-Glossary-Generator)'s
scan and travels inside the Registry.

## Why — the Registry

In PDC the same three facts about a column — its business term, its tags, and
its sensitivity — get decided in more than one place, by hand. The glossary
says one thing; a hand-authored identification rule can silently say another
(`PII` vs `pii`, a stale term binding, an off-vocabulary tag), and the drift
only surfaces in an audit.

The **Classification Registry** (`classification-registry/1`) is the contract
that closes that gap — written by one app, read by this one, mirroring PDC's
own split between the Business Glossary and Data Identification:

1. **[Glossary Generator](https://github.com/jporeilly/PDC-Glossary-Generator)**
   (its own repo) builds the reviewed business glossary and, at export,
   authors the Registry — one row per governed concept carrying the term,
   governed tags (from a controlled allow-list), floor-lifted sensitivity,
   the scan's **detection seeds** (induced value regexes like `^CSCU-\d{6}$`
   and profiled reference-value lists), the physical source columns, PK/FK
   facts, and the full governed tag vocabulary with its audit provenance.
2. **Policy Generator** (this repo) **reads that Registry** and owns the
   Data Identification lifecycle:

   | Stage | What it does | Status |
   | --- | --- | --- |
   | **Author** | one Data Pattern (`patternsRules` JSON) per regex seed, one Dictionary (`dictionariesRules` JSON + values CSV) per reference-list seed — each assigning the Registry's governed tags and business term | **working** |
   | **Reconcile** | verify each concept's minted `term_id` (backfilled into the Registry by the Glossary app's Resolve step) and bind methods to it | next |
   | **Deploy** | import the methods over the public API (v3) and trigger `DATA_IDENTIFICATION` bulk jobs scoped to the right entities | next |
   | **Drift-check** | compare deployed methods' Assign-Tags and PDC's live tag facet against the Registry's governed vocabulary — flag methods stamping off-vocabulary tags, governed tags nothing emits, and broken term bindings | next |

Because both apps draw from the same Registry row, the glossary term, the
tags a method stamps, and the sensitivity can never quietly diverge — that is
the point of the contract. The schema is documented field-by-field in
[docs/CONTRACT.md](docs/CONTRACT.md).

## What it does

- **Load** — drag-drop a Registry into the web UI (or give a path), and read
  the contract summary: concepts, detection seeds, resolved term ids,
  governed tags, off-vocabulary warnings. When this repo is cloned beside or
  inside the Glossary checkout (the lab VM's `~/PDC-Demo` layout), the app
  **auto-discovers** `glossary_generator/registries/registry.*.json` and
  lists what it found — a single match loads itself.
- **Author** — preview the method manifest (every rule with its term and
  binding), then download the set as one zip: `Patterns/`, `Dictionaries/`
  (+ values CSVs), `INDEX.csv` — the exact shapes PDC's
  **Management → Data Identification → Import** accepts (the same shapes the
  CSCU Technical Track teaches, so a steward can read every field). Tags are
  re-filtered against the Registry's embedded allow-list at authoring time;
  off-vocabulary tags are refused, never imported.
- **Learn as you go** — the UI teaches the way the Glossary app does:
  expandable **"Under the hood"** panels explain every concept (what each
  summary number means, how a seed becomes a method field-by-field) and show
  the exact calls each step runs — this app's own API, the manual PDC import
  path, and the deploy-stage public-API calls, badged *roadmap* until they
  ship.
- **Same engine on the CLI** — `python -m policy_generator info|author`,
  zero dependencies, for scripted or headless use.

## Repository layout

```text
policy_generator/       the app: engine (registry.py, author.py), CLI,
                        web UI (app.py + templates/), launchers, VERSION
docs/
  CONTRACT.md           the classification-registry/1 schema, field by field
  CHANGELOG.md          release history
  INSTALL.md            install & lab-setup guide (markdown master)
  lab-setup.docx        the same guide in the course design, generated
courseware/             one workshop set per scenario (CSCU today), same
  CSCU/                 course design + docx builder as the Glossary repo
```

## Install & run

**Requirements:** Python 3.9+. PDC is reached only when *you* import and run
the methods — the app itself stays offline. **No LLM.**

The full guide — including cloning into the lab VM's `~/PDC-Demo` Glossary
checkout — is [docs/INSTALL.md](docs/INSTALL.md) (also as
[docs/lab-setup.docx](docs/lab-setup.docx)). The short version:

```bash
git clone https://github.com/jporeilly/PDC-Policy.git
cd PDC-Policy/policy_generator
./run.sh                         # Linux/macOS → http://127.0.0.1:5001
.\run.ps1                        # Windows (or double-click run.bat)
```

The launcher manages a local `.venv` (Flask is the only dependency) and
defaults to **port 5001** so the Glossary Generator (5000) runs alongside.

**CLI** (no dependencies at all):

```bash
python -m policy_generator info                    # newest auto-discovered Registry
python -m policy_generator author -o out/ --prefix CSCU
python -m policy_generator author path/to/registry.<id>.json --zip methods.zip
python -m policy_generator.selftest                # offline self-test (20 checks)
```

## Courseware

[`courseware/`](courseware/) mirrors the Glossary repo's per-scenario workshop
sets: the CSCU set carries
[Workshop-Policy-Generator-CSCU.md](courseware/CSCU/Workshop-Policy-Generator-CSCU.md)
(the authoritative markdown master) and its generated `.docx`
(`courseware/CSCU/tools/build-docx.py`, same course design and template). It
picks up where the Glossary Generator's CSCU app workshop ends — at the
Registry hand-off — and walks Registry → `info` → `author` → PDC import →
run Data Identification → verify, with checkpoints.

## Documentation

| Document | What it covers |
| --- | --- |
| [docs/INSTALL.md](docs/INSTALL.md) | Install & lab setup: prerequisites, cloning (workstation or `~/PDC-Demo`), web UI, CLI, selftest, troubleshooting |
| [docs/lab-setup.docx](docs/lab-setup.docx) | The same guide in the course design (generated from INSTALL.md) |
| [docs/CONTRACT.md](docs/CONTRACT.md) | The `classification-registry/1` schema and the guarantees both apps share |
| [docs/CHANGELOG.md](docs/CHANGELOG.md) | Release history (the app version lives in `policy_generator/VERSION`) |
| [courseware/](courseware/) | One workshop set per scenario (CSCU today; RETAIL/HEALTH/MFG plug in the same way) |

The shared lab (PDC VM, demo PostgreSQL + MinIO, scenario loads) is owned by
the Glossary repo — its `data_sources/lab/lab-setup.docx` (Parts A–I) is the
authoritative build guide.

## Status

The **author** stage works end-to-end from a real Registry — over the web UI
or the CLI — and is covered by the offline selftest. Reconcile, deploy and
drift-check are the roadmap, in that order — drift needs deployed methods to
check, which needs reconcile-and-deploy first.

*All scenario data referenced here (CSCU et al.) is fictional and generated
for training.*
