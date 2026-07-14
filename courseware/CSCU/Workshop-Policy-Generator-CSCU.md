# Workshop — Author Data Identification with the Policy Generator

*Copper State Credit Union (CSCU) scenario · app 1.1.x · validated against PDC 11.0.0*

**Primary role:** Data Steward / Data Developer
**Estimated time:** 45–60 min
**Prerequisites:** the Glossary Generator workshop completed on CSCU — the
glossary reviewed and imported into PDC, and the app's Generate step has
written the **Classification Registry**
(`glossary_generator/registries/registry.<glossary-uuid>.json`). Python 3.10+
on the host. PDC reachable over HTTPS with a user allowed to import under
**Management → Data Identification**.

---

## 1. The scenario

**Copper State Credit Union**'s governed glossary now exists in PDC — but the
catalog still has to *recognize* CSCU's data on its own. New tables arrive,
documents land in the bucket, and every scan asks the same question: which
columns hold member numbers, routing numbers, risk ratings, SAR statuses?

Data Identification answers it with **methods** — Data Patterns and
Dictionaries that classify, tag and bind columns to business terms. Workshop 5
and Technical Track Module 03 taught you to author them **by hand**. This
workshop authors the same methods **from evidence**: the Registry the Glossary
Generator exported carries, for every governed concept, the **detection
seeds** its scan induced from profiled data — value-format regexes like
`^CSCU-\d{6}$` and reference-value lists (risk ratings, SAR statuses, account
types). The Policy Generator turns those seeds into import-ready methods that
stamp **only governed tags** and bind **only governed terms**.

Because both apps read the same Registry row, the term a method binds, the
tags it stamps, and the sensitivity can never quietly diverge — that is the
contract.

## 2. What you will build

An import-ready **Data Identification method set** for CSCU — one Data
Pattern (`patternsRules` JSON) per regex seed, one Dictionary
(`dictionariesRules` JSON + values CSV) per reference-list seed, each
assigning the Registry's governed tags (`pci`, `aml`, `lending`, … always
lower-case) and its business term — plus an `INDEX.csv` manifest. Then you
import the set into PDC, run Data Identification, and verify the catalog now
tags CSCU's data with the governed vocabulary.

## 3. Lab flow

### Step 1 — Fetch the Registry

The Glossary Generator wrote the Registry at Generate time, one file per
glossary, regenerated on every export:

```sh
# on the host that ran the Glossary Generator
ls ../PDC-Glossary/glossary_generator/registries/
#   registry.<glossary-uuid>.json
```

Copy it somewhere handy (or reference it in place). If you re-reviewed the
glossary since, re-Generate first — export time is the latest reviewed state.

### Step 2 — Read the contract with `info`

```sh
python -m policy_generator info path/to/registry.<uuid>.json
```

(When this repo is cloned into the same folder as `glossary_generator/` —
the lab VM's `~/PDC-Demo` layout — you can omit the path: the newest
Registry is auto-discovered, in the CLI and on the web UI's Load card.)

`info` prints what the Registry carries before you author anything: the
glossary name and id, concept count, how many concepts carry detection seeds,
how many have **resolved term ids**, and the governed-tag count.

[SCREENSHOT: `info` output for the CSCU registry — concepts, seeds, resolved term ids, governed tags]

Two readings matter:

- **`resolved term ids: 0`** means the Glossary app's **Resolve term ids**
  step hasn't been run since import (or the Registry wasn't re-exported after
  it). Authoring still works — rules bind the business term **by name** until
  ids are resolved — but run Resolve and re-export for id-solid bindings.
- **off-vocabulary tags: 0** is the healthy state. Anything else is drift out
  of the Glossary app — fix it there; the author stage refuses off-vocabulary
  tags rather than letting them into PDC.

### Step 3 — Author the method set

```sh
python -m policy_generator author path/to/registry.<uuid>.json -o out/ --prefix CSCU
```

The output mirrors what PDC's import expects:

```text
out/
  Patterns/          one cscu_<term>.json per regex seed             (patternsRules)
  Dictionaries/      one cscu_<term>_rule.json + cscu_<term>.csv
                     per reference-list seed                         (dictionariesRules)
  INDEX.csv          kind, rule name, file, term, term_id
  README.txt         import pointers
```

Concepts without seeds are listed as **skipped**, with the reason — a concept
detected only by name/context has no evidence to author from, and guessing is
exactly what this pipeline exists to avoid.

`--zip out/cscu-methods.zip` writes the same set as one zip if you prefer a
single artifact.

### Step 4 — Review before you import

Open one pattern and one dictionary rule — every field is one the CSCU
Technical Track taught, so read it like a steward:

- **name** — prefixed (`CSCU …`), so your methods group together in PDC.
- **column-name hint** — a regex derived from the Registry's physical
  `sources[]` (the real columns the term maps to), not guessed from the term.
- **contentPatterns** — the induced value signature (e.g. `^CSCU-\d{6}$` for
  member numbers). This came from profiled sample values.
- **actions → applyTags** — governed, lower-case, re-filtered against the
  Registry's embedded allow-list at authoring time.
- **assignBusinessTerm** — the governed term the Glossary app owns.

Open a dictionary's values CSV and confirm the reference values are the ones
profiling actually saw (risk ratings, SAR statuses, account types).

`INDEX.csv` is your review manifest: one row per method with its term and
(when resolved) term id.

[SCREENSHOT: a CSCU pattern rule JSON beside its INDEX.csv row]

### Step 5 — Import into PDC

**Management → Data Identification**:

- **Patterns → Import** — select the files under `out/Patterns/`.
- **Dictionaries → Import** — select each `*_rule.json` with its values CSV
  under `out/Dictionaries/`.

[SCREENSHOT: PDC Data Identification import dialog with the CSCU method set]

The methods appear alongside the built-ins, grouped by the `CSCU` prefix.

### Step 6 — Run Data Identification

Run **Data Identification** on the CSCU sources
(`CopperState_Core_Banking`, then **Scan Files** on
`CopperState_Documents`) so the new methods execute — same as Workshop 5.

[SCREENSHOT: Data Identification job completed on CopperState_Core_Banking]

### Step 7 — Verify the governed vocabulary landed

- Search/filter by tag: the governed facets (`pci`, `aml`, `member`, …) now
  match columns your methods classified — and **only** governed tags appear;
  the method set cannot introduce a stray facet.
- Open `cscu_core.members.mbr_no`: the member-number pattern matched, the
  column carries the term *Member Number* and its tags.
- Check a dictionary hit: `suspicious_activity.risk_rating_cd` classified from
  the risk-rating reference values.

[SCREENSHOT: a column tagged by a CSCU method, showing term + governed tags]

## 4. Checkpoints

| # | Check | Evidence |
| --- | --- | --- |
| 1 | Registry read clean | `info`: concepts with seeds > 0, off-vocabulary 0 |
| 2 | Method set authored | `out/Patterns/` + `out/Dictionaries/` + `INDEX.csv` |
| 3 | Every tag governed | rule `applyTags` ⊆ the Registry allow-list (spot-check) |
| 4 | Methods imported | Data Identification lists the `CSCU`-prefixed methods |
| 5 | Identification ran | job completed on both CSCU sources |
| 6 | Vocabulary landed | governed tag facets match; `mbr_no` carries *Member Number* |

## 5. Where the story continues

You authored and deployed by hand what the contract makes automatic. The
Policy Generator's remaining stages take over from here: **reconcile** binds
each method to its minted `term_id` once the Registry is re-exported after
Resolve; **deploy** imports the methods and triggers the
`DATA_IDENTIFICATION` jobs over the public API (v3); **drift-check** compares
what deployed methods stamp — and PDC's live tag facet — against the
Registry's governed vocabulary, flagging off-vocabulary tags, governed tags
nothing emits, and broken term bindings.

---

*All Copper State Credit Union data — members, accounts, transactions, SARs
and documents — is fictional and generated for training.*
