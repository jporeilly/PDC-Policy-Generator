# PDC Policy Generator

**Version:** 1.1.1 (`policy_generator/VERSION`) · targets **Pentaho Data Catalog 11.0.0** (public API v3) · [changelog](docs/CHANGELOG.md)

The second half of a two-app governance pipeline. The
[Glossary Generator](https://github.com/jporeilly/PDC-Glossary-Generator)
builds the reviewed business glossary and, at export, authors a
**Classification Registry** — one row per governed concept, carrying the
term, governed tags, sensitivity, the scan's **detection seeds** (induced
value regexes and profiled reference-value lists), the physical source
columns, PK/FK facts, and the full governed tag vocabulary with its audit
provenance.

**This app reads that Registry** and manages PDC's Data Identification
side of the contract:

1. **Author** — emit the Data Identification methods: a Data Pattern
   (`patternsRules` JSON) per regex seed, a Dictionary
   (`dictionariesRules` JSON + values CSV) per reference-list seed, each
   assigning the Registry's governed tags and business term. *(working)*
2. **Reconcile** — after the glossary is imported into PDC, verify each
   concept's minted `term_id` (backfilled into the Registry by the
   Glossary app's Resolve step) and bind methods to it. *(next)*
3. **Deploy** — import the methods over the public API and trigger
   `DATA_IDENTIFICATION` bulk jobs scoped to the right entities. *(next)*
4. **Drift-check** — compare deployed methods' Assign-Tags and PDC's live
   tag facet against the Registry's governed vocabulary; flag methods
   stamping off-vocabulary tags, governed tags nothing emits, and terms
   whose bindings broke. *(next)*

Because both apps draw from the same Registry row, the glossary term, the
tags a method stamps, and the sensitivity can never quietly diverge —
that is the point of the contract.

## Quick start

**Web UI** (mirrors the Glossary Generator's launcher — venv-managed, port
5001 so both apps run side by side):

```bash
cd policy_generator
./run.sh            # Linux/macOS        → http://127.0.0.1:5001
.\run.ps1           # Windows PowerShell (or double-click run.bat)
```

Load the Registry (drag-drop or path), read the contract summary, preview the
method manifest, author and download the zip.

**CLI** (same engine, no dependencies at all):

```bash
# author the Data Identification artifacts from a Registry the Glossary
# Generator wrote (glossary_generator/registries/registry.<id>.json)
python -m policy_generator author path/to/registry.<id>.json -o out/ --prefix CSCU

# offline self-test (no PDC, no network)
python -m policy_generator.selftest
```

`author` writes `out/Patterns/*.json`, `out/Dictionaries/*_rule.json` +
values CSVs, and an `INDEX.csv` — the exact shapes PDC's
**Management → Data Identification → Import** accepts (the same shapes the
CSCU Technical Track teaches, so a steward can read every field).

## The contract

The Registry schema (`classification-registry/1`) is documented in
[docs/CONTRACT.md](docs/CONTRACT.md). It is written by the Glossary
Generator at Generate time and is the **only** input the author stage
needs; reconcile / deploy / drift additionally need PDC API credentials.

## Courseware

[`courseware/`](courseware/) mirrors the Glossary repo's per-scenario workshop
sets: the CSCU set carries
`Workshop-Policy-Generator-CSCU.md` (the authoritative markdown master) and
its generated `.docx` (`courseware/CSCU/tools/build-docx.py`, same course
design and template). It picks up where the Glossary Generator's CSCU app
workshop ends — at the Registry hand-off.

## Status

The **author** stage works end-to-end from a real Registry — over the web UI
or the CLI — and is covered by the offline selftest. Reconcile, deploy and
drift-check are the roadmap, in that order — drift needs deployed methods to
check, which needs reconcile-and-deploy first.

*All scenario data referenced here (CSCU et al.) is fictional and generated
for training.*
