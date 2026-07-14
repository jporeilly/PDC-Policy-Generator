# Changelog

All notable changes to the Policy Generator are recorded here.
Format follows [Keep a Changelog](https://keepachangelog.com/); this project uses
date-based releases. The app version lives in `policy_generator/VERSION` (the
single source of truth — the web UI banner and
`python -m policy_generator --version` both read it). Versioning starts at
**1.1.1** by project decision.

> The **1.1.x** line is the first working release: the **author** stage of the
> author → reconcile → deploy → drift-check lifecycle, end-to-end from a real
> Classification Registry, with the CLI, the local web UI, and the CSCU
> courseware set.

## [1.1.2] — 2026-07-14

### Changed

- **Repository renamed** `PDC-Policy` → **`PDC-Policy-Generator`**, matching
  the companion `PDC-Glossary-Generator`. GitHub redirects the old URL; all
  clone commands and cross-references swept.

### Added — Registry auto-discovery (clone beside the Glossary app, zero config)

- `registry.discover_registries()`: probes `POLICY_REGISTRY_DIR`, then the
  repo's parent folder for `glossary_generator/registries/registry.*.json` —
  the layout when PDC-Policy-Generator is cloned **inside** the Glossary checkout
  (the lab VM's `~/PDC-Demo`) — then sibling `PDC-Glossary`/
  `PDC-Glossary-Generator` checkouts. Newest first.
- **Web UI**: `GET /api/registries` + a "Found on this machine" picker on the
  Load card (glossary name, concept count, modified time, one-click Load);
  a single match loads automatically.
- **CLI**: `info` and `author` now take the registry path as optional — when
  omitted, the newest discovered Registry is used (and announced).

### Added — install & lab-setup guide

- **`docs/INSTALL.md`** — the authoritative setup master: overview,
  prerequisites (pointing at the Glossary repo's `lab-setup.docx` Parts A–I
  for the shared lab), Part A get the repo (including cloning inside the lab
  VM's `~/PDC-Demo` Glossary checkout as a nested repo, with the
  `.git/info/exclude` hygiene line), Part B web UI, Part C CLI, Part D
  selftest verification, Part E updating, Part F the PDC import side,
  Part G troubleshooting.
- **`docs/lab-setup.docx`** — generated from `INSTALL.md` by
  `courseware/CSCU/tools/build-docx.py` (new DOCS entry; markdown master
  stays authoritative), Word-COM verified.

## [1.1.1] — 2026-07-14

### Added — the engine and CLI

- **Registry reader** (`registry.py`): loads and validates
  `classification-registry/1` files written by the Glossary Generator
  (envelope validation factored into `validate_registry(dict)` so uploads
  validate identically to files); contract summary (`info` command),
  unresolved-term detection.
- **Author stage** (`author.py`): one Data Pattern (`patternsRules` JSON) per
  regex seed, one Dictionary (`dictionariesRules` JSON + values CSV) per
  reference-list seed — the exact shapes PDC 11.0.0's
  **Management → Data Identification → Import** accepts (the CSCU Technical
  Track shapes). Tags re-filtered against the Registry's embedded
  `tag_vocabulary.allow_list` at authoring; column-name hints derived from
  `concepts[].sources`; `INDEX.csv` manifest; directory or single-zip output.
- **CLI** (`python -m policy_generator info|author`) with `--prefix` and
  `--zip`; Windows-console-safe output.
- **Offline selftest** (`python -m policy_generator.selftest`, 20 checks — no
  PDC, no network), cross-verified against the real glossary-side Registry
  writer.
- **Contract doc** (`docs/CONTRACT.md`): the `classification-registry/1`
  schema field-by-field, and the guarantees both apps share.

### Added — local web UI, same shape as the Glossary app

- **Flask front end** (`policy_generator/app.py` + `templates/index.html`):
  load a Registry (drag-drop upload or local path), read the contract summary
  (concepts, seeds, resolved term ids, governed tags, off-vocabulary
  warning), preview the method manifest, author and download the zip. The
  page teaches as it goes, copying the Glossary app's help components:
  expandable **"Under the hood" hoodcards** with `fielddefs` concept grids
  (what the summary numbers mean, how a seed becomes a method) and
  color-coded **apicall blocks** showing the exact calls each step runs —
  this app's own API, the manual PDC UI path, and the deploy-stage public
  API v3 calls (marked *roadmap*), including the internal `/api/start-job`
  401 caveat. Flask
  was chosen deliberately: it matches the Glossary Generator (one stack, two
  apps, no build toolchain), and the FastAPI evaluation on the glossary side
  was deferred (`REVIEW.md` there records the trigger).
- **Launchers** (`run.sh` / `run.ps1` / `run.bat`), ported from the Glossary
  app: venv-managed, requirement-stamped, pre-flight checks. Default port
  **5001** so the Glossary Generator (5000) runs alongside.
- **`requirements.txt`** — `flask` only; the author stage stays offline.
  (reconcile / deploy will add `requests` for the public API.)
- API: `GET /api/version`, `POST /api/load`, `POST /api/preview`,
  `POST /api/author` (zip download).

### Added — project structure mirrors the Glossary Generator

- **`policy_generator/VERSION`** — single source of truth for the app
  version; `__init__.py` reads it (with a literal fallback) and `--version`
  reports it, the same pattern as the Glossary app's `VERSION` beside
  `app.py`.
- **This changelog** (`docs/CHANGELOG.md`), in the same Keep-a-Changelog,
  date-based format as the Glossary Generator's.
- **Courseware** (`courseware/`): the CSCU workshop set for this app —
  `Workshop-Policy-Generator-CSCU.md` (authoritative markdown master, amber
  `[SCREENSHOT]` markers) covering Registry → `info` → `author` → PDC import
  → run Data Identification → verify, plus the set README and the
  `tools/build-docx.py` + `template.docx` Word-guide builder ported from the
  Glossary repo (markdown masters stay authoritative; the `.docx` is
  generated and Word-COM verified).

## Earlier

The authoring engine began life inside the Glossary Generator (its
`classification/` engine and in-app **Draft policies (AI)** agent, which
remains the quick path there). This repo carves the lifecycle owner out into
its own app; reconcile, deploy and drift-check are the roadmap, in that order.
