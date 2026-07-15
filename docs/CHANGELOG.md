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

## [1.5.0] — 2026-07-15

### Fixed — import format rewritten against live PDC exports (the Gson error)

PDC's import rejected our zip (`Expected BEGIN_OBJECT but was BEGIN_ARRAY`):
the `patternsRules`/`dictionariesRules` shapes we emitted were the *Rules-tab
display view*, never the import format. Ground truth was established from a
live 11.0 instance's own **Export** zips (95 dictionaries + 42 patterns
scanned) plus the official docs' sample images:

- **Emitters rewritten to the export envelope format**: DataPattern
  (`regexMatch.regex`, `profilePatterns` from the signature,
  `metadataHints.aliases` from the physical sources, JsonLogic rule on
  `regexScore`/`profilePatternScore`/`metadataScore`) and Dictionary
  (`csv` pairing, `rowCount`, JsonLogic on `similarity`/`metadataScore`).
  Each JSON file is a **single object**; ids are deterministic UUID5s.
- **`applyTags` uses the live `{"name": tag}` shape** (the 2020 docs' and
  TT's `{"k": …}` would have been silently ignored). `assignBusinessTerm`
  included best-effort as an action (`{name, id}`) — no built-in export
  demonstrates it; unknown fields are ignored and terms are applied by
  mapping regardless.
- **Import layout mirrors the exports**: the download now bundles
  `patterns-import.zip` (flat json per pattern) and
  `dictionaries-import.zip` (nested zip per dictionary pairing json +
  **Term**-header CSV) + INDEX.csv — upload each zip whole on its page
  (Data Operations → Data Identification Methods).
- Field-by-field structural diff against the real exports: pattern envelope
  and rules match exactly; UI (inspector, import instructions, checklist)
  and selftest (24 checks) updated.

## [1.4.6] — 2026-07-14

### Changed

- The skipped-concepts section gained a visible expandable explainer
  ("What these groups mean — and what to do about each"): a color-keyed
  legend spelling out each group's mechanism and its action — amber is the
  seed worklist (curated seed or profiling re-scan), teal/purple/gray need
  nothing (mapping-applied, business rules, table/folder grain) — plus the
  three-mechanism framing and the drift-check closing note. Previously this
  lived only in hover tooltips.

## [1.4.5] — 2026-07-14

### Added — diagram pipeline: live mermaid in markdown, rendered PNGs in the docx

- CONTRACT.md and INSTALL.md gained mermaid diagrams (contract anatomy +
  lifecycle; install topology + workflow) alongside the README's pair — all
  six validated with mermaid-cli.
- **`docs/tools/render-diagrams.py`**: regenerates every diagram's canonical
  PNG in `images/` from the live mermaid blocks (2× scale, white background)
  so the images can never drift from the source.
- **`build-docx.py` embeds mermaid as images**: a ```mermaid fence in
  INSTALL.md becomes the corresponding rendered PNG in `lab-setup.docx`
  (never raw diagram source in a course guide). Word-COM verified: 2 inline
  images embedded.
- Image audit across all three repos: every markdown image reference
  resolves; INSTALL's front-matter version line refreshed.

## [1.4.4] — 2026-07-14

### Changed

- **Rule-tester examples are now derived from each rule** instead of a
  hardcoded `CSCU-104233`: patterns get a sample **synthesized from their
  own regex** (a small exemplar generator handling literals, escapes,
  classes, groups/alternation and quantifiers — every generated example is
  verified against the regex before use, e.g. `^LN\-\d{6}$` → `LN-104233`,
  the SSN shape → `104-23-3958`, email → `ac@me.sa`); dictionaries use their
  first reference value. Falls back to a neutral placeholder for shapes the
  generator doesn't understand.

## [1.4.3] — 2026-07-14

### Added

- **Reconcile progress bar**: reconcile now runs in batches of 8 terms
  (`POST /api/reconcile {offset, limit}`) — the UI draws an exact progress
  bar (`n/total terms`) and the results table fills in live as batches
  return. A call without a limit still reconciles everything in one shot
  (CLI/API compatibility). Also fixed the run-together summary line
  ("0 missing — 44 id(s) can be applied…").

## [1.4.2] — 2026-07-14

### Changed — skipped concepts classified and color-coded by mechanism

- The flat skipped-terms list is now grouped into four color-coded buckets,
  each with a count and hover explanation: **amber** — should be
  value-recognizable (add a `curated_seeds` entry or re-scan with
  profiling); **teal** — applied by mapping (the Glossary app's Apply step
  governs them on their mapped columns); **purple** — business-rule
  territory (free text / semantics); **gray** — table/folder-level concepts.
  Classification is server-side (`_bucket()` in `app.py`), verified against
  19 real CSCU term names.
- The CSCU Policy workshop gained a matching **"Why most concepts have no
  method — the three mechanisms"** section (Apply / identification /
  business rules, how to read the color groups, drift-check closes the
  loop) — PDC-Scenarios commit `1a5cbdb`.

## [1.4.1] — 2026-07-14

### Changed

- The skipped-concepts panel now teaches the three-mechanism model instead
  of just listing terms: seedless concepts are still fully governed — the
  Glossary app's **Apply** step binds term/tags/sensitivity onto the mapped
  columns; identification methods only add **value-based recognition**;
  semantic conditions are **business rules**. It also says how to seed a
  concept that *should* be value-recognizable (re-scan with profiling, or a
  domain-pack `curated_seeds` entry).

## [1.4.0] — 2026-07-14

### Added — the Reconcile stage (working), rule inspector, import checklist

- **Reconcile page**: connect to PDC (Keycloak-first auth with `/auth`
  fallback — `pdc.py`, a verbatim stdlib subset of the Glossary app's
  battle-tested client, including the never-facet-search-by-term fix), then
  reconcile the loaded Registry: every concept's term looked up in PDC and
  badged **verified / resolved / mismatch / missing**. One click stamps the
  PDC ids into the loaded Registry (in memory) so re-authored rules bind by
  id; `GET /api/registry/export` downloads the reconciled copy. The token
  lives in memory only; passwords are never stored. Still zero dependencies
  beyond Flask.
- **Rule inspector**: click any preview row to expand the governed tags, the
  column hint, the **full rule JSON exactly as PDC imports it**, and a live
  tester — try a sample value against the pattern regex, or check membership
  of the dictionary's reference values (shown as chips, first 200).
- **Import checklist** on the import card, shown after a download: the six
  workshop checkpoints (INDEX read, patterns imported, dictionaries + CSVs,
  identification ran, Scan Files, only governed facets) with per-item help,
  persisted per glossary in the browser; completing them drives workflow
  steps 4 (Import) and 5 (Verify) on the stepper.
- API: `POST /api/pdc/connect`, `POST /api/reconcile`,
  `POST /api/reconcile/apply`, `GET /api/registry/export`; `/api/preview`
  now returns regex/signature/column-hint/tags/values/rule per method.

## [1.3.1] — 2026-07-14

### Added

- **Favicon** (`static/favicon.svg`, served at `/favicon.svg` and
  `/favicon.ico`): a governance shield with a check, in the app's navy/teal
  palette — the shield is the policy, the check is the Registry allow-list.

## [1.3.0] — 2026-07-14

### Changed — same look and feel as the Glossary Generator

The web UI is now a true sibling of the Glossary app, built from its design
system (same CSS variables and components):

- **Sidebar** with the brand block (app name + `load · review · author ·
  import · vX.Y.Z`), nav — Author active; Reconcile / Deploy / Drift-check
  visible but disabled with *soon* badges and tooltips explaining each
  future stage — and a **Registry status pill** (green dot + glossary name
  once loaded).
- **Workflow stepper** (the Glossary app's `flow` component): Load →
  Review → Author → Import (PDC) → Verify (PDC), live done/active states
  driven by app state, each step tooltip'd; clicking scrolls to its card.
- **Four themes** (light / teal / pentaho / dark — identical palettes to the
  Glossary app), picked on a new **Settings page**, persisted in
  localStorage. Serif page/card headings with the gradient accents,
  identical buttons, fields, notes, tables.
- **Many more tooltips**: `?` help circles and title tooltips on every
  control, stat tile, table header, nav item and workflow step (35+),
  plus workflow explanations — an intro "How this app fits" panel and
  step-by-step guidance in the result messages (e.g. the download toast
  points at workflow step 4).

## [1.2.2] — 2026-07-14

### Changed — flat PDC-Demo layout

- `install-pdc-demo.sh` now clones into a hidden `.pdc-policy-generator/`
  and links the app **flat at the top level**: `PDC-Demo/policy_generator`
  beside `glossary_generator`, `PDC-Demo/courseware` (into PDC-Scenarios),
  and the app README kept separate as `README-Policy.md`. An existing
  `PDC-Policy-Generator/` layout is migrated in place. The PDC-Scenarios
  bootstraps (bash + PowerShell, which uses junctions) do the same.

## [1.2.1] — 2026-07-14

### Fixed

- Registry auto-discovery now also probes `PDC-Demo/glossary_generator/`
  from a **sibling** position, so cloning the app beside `~/PDC-Demo` (in
  the home directory) discovers the Registry exactly like the nested layout.

## [1.2.0] — 2026-07-14

### Changed — courseware moved to PDC-Scenarios; the installer is vertical-aware

- **Courseware moved out**: this app's workshops now live in the
  [PDC-Scenarios](https://github.com/jporeilly/PDC-Scenarios) repo,
  separated per app within each vertical (`courseware/<ID>/Policy/` beside
  `Platform/` and `Glossary/`). The repo keeps `docs/tools/` (the Word-guide
  builder) so `docs/lab-setup.docx` still regenerates from `INSTALL.md`.
- **`install-pdc-demo.sh` is vertical-aware**: pass a vertical
  (`CSCU`/`RETAIL`/`HEALTH`/`MFG`) and it clones/updates PDC-Scenarios beside
  the app — sparse, `--no-checkout` first so only the selected vertical's
  data kit + courseware ever touch disk — and re-runs detect the selected
  vertical from the sparse state and refresh it. The Glossary repo gained a
  twin script; either keeps the shared PDC-Scenarios checkout fresh.
- Docs + UI swept for the new courseware home (README, INSTALL.md, the
  import-step hint on the web UI).

## [1.1.3] — 2026-07-14

### Changed — the VM install is app-only

- `install-pdc-demo.sh` now **sparse-clones** (`--filter=blob:none
  --sparse`, checkout set to `policy_generator/`): the lab VM gets the app
  and root files only — courseware and docs never land on the deployment.
  Updates remain plain fast-forward pulls; existing full clones keep working.

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

### Added — VM installer script

- **`install-pdc-demo.sh`** (repo root): install/update the app inside
  the lab VM's `~/PDC-Demo` Glossary checkout — verifies the folder, clones
  on first run (into `PDC-Policy-Generator/`, excluded from the outer repo's
  `git status`) or fast-forward-pulls thereafter, prints the app version and
  runs the offline selftest. Works as a curl one-liner on a fresh VM;
  `POLICY_REPO_URL` / `PDC_DEMO_DIR` overrides for forks and odd layouts.

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
