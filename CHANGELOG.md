# Changelog

## [1.10.11] - 2026-08-21

### Fixed - a dictionary value with a comma in it killed the import

Deploy reported COMPLETED and 18 of 31 dictionaries were not in the catalog.
The emitter built the one-column values CSV by joining values with newlines,
and `water_systems.conservation_focus` holds "Expanding metro area, new
customer acquisition, infrastructure growth". PDC's importer read a 1-column
header, hit a 3-field row, threw CSVFieldNumDifferentException - and abandoned
the REST OF THE ZIP. The 13 dictionaries queued before the bad row landed; the
18 after it did not; the worker still reported COMPLETED, which is the failure
mode pdc.py already warns about two functions above the one that hit it.

Both emitters now write RFC 4180 through csv.writer - the dictionary values
and INDEX.csv, where a term name carrying a comma would shift every column
after it. Tested against the values that actually broke it, plus quotes and
embedded newlines.

### Fixed - a Disable button that was disabled

"Disable built-ins" and "Restore" sat `disabled` until "Count them" had been
clicked, and nothing on screen said so. Field-caught mid-walk: "I've clicked
Disable built-ins several times, seems as though it's disabled (joke)" - which
was the correct diagnosis. The action needs the count for its own confirm
prompt, so it now fetches its own when nobody has counted, and both buttons
stand alone. Disable is the primary action on that card and now looks like it.

### Added - the built-in disable is confirmed against the estate

The endpoint reported `changed` - the number of PATCH calls that did not
raise. That is not the number of methods that are off, and this action is the
only thing standing between a custom-only programme and 137 built-in shapes
competing with it during the next identification run. It now READS EVERY
TARGET BACK and reports the count the estate agrees with; anything PDC
accepted but did not apply is named, with its live state, and the card says an
identification job will still classify against it. A dry run reports no
verification, because it changed nothing.

The test fake grew to match: it honours an enable/disable rather than always
answering from a static table, it has a detail record for the built-in at all
(anything READING one hit a KeyError before), and it can be told to accept a
write and ignore it - which is the case the read-back exists for.

## [1.10.10] — 2026-08-21

### Changed — the Load overview explains the stages as tiles

The "five stages" card under the workflow diagram now lays the stages out as
tiles — numbered dot, title, explanation, and a **Go to** button that jumps
straight to the page — the same treatment the Glossary Generator's Home page
uses, so the two apps read as one suite. Load itself is marked *You are here*,
and Report keeps its "not a step but a read" status with an unnumbered marker.
The prose is unchanged; only its shape moved.

## [1.10.9] — 2026-08-20

### Fixed — the threshold type that stopped every pattern from firing

Live-bisected. Our Data Patterns compared `confidenceScore` against the JSON
**number** `0.5`; PDC's JsonLogic does not coerce, so the comparison never
became true. The methods imported cleanly, passed drift, and silently never
matched — worse than the columnCardinality bug, which was at least rejected at
import. Both PDC's own `USA_SSN` and our own dictionaries gate on the **string**
`"0.5"`, and the dictionaries were the control sample all along: they fired in
the same run where every pattern tagged nothing.

### Added — guards for the two silent failures found today

- **Deploy refuses methods that would bind by NAME** (409, naming the terms and
  why the ids went missing). A run on 2026-08-19 shipped 115 methods of which 40
  bound by name, because Reconcile's ids live in memory and a restart discarded
  them. The dry run is exempt and reports `name_binding` instead — it writes
  nothing, and it is how a steward should find this.
- **Identification refuses a never-profiled scope.** Patterns match against the
  stored PROFILE, not the live table: the same 55 methods tagged 9 columns in a
  freshly profiled table and 1 in a stale one, in the same job. Every run now
  reports each entity's `profiledAt`.
- **Author skips boolean sources** and flags **ambiguous shapes** — a content
  regex claimed by more than one method identifies none of them (one induced
  shape backed eight concepts here, and a free-text column came back bound to
  all eight).

### Added — the read-back, and the reads that made today possible

- `POST /api/pdc/identified` — what identification actually did, column by
  column, judged against the Registry. A term alone no longer counts as a match:
  the Glossary's Apply binds terms too, so the method's **tags** decide, and
  `expected_term_only` names the difference.
- `POST /api/pdc/entity` — everything PDC holds on one entity, `features`
  verbatim. It proved the rating defect in minutes.
- `POST /api/pdc/method` — one method, whole. Diffing ours against a built-in is
  what found the threshold bug.
- `POST /api/pdc/job` — what became of a job, with the per-job lines that say
  whether the scope was covered; and `recent` for when the id is not to hand.
- `POST /api/pdc/builtins` — count, disable or restore PDC's 137 shipped
  methods. Dry run by default, never touches a custom method, reversible.
- `POST /api/pdc/entities` — name search, feeding a table picker on Deploy, so a
  scope is chosen rather than pasted as a uuid.

99 tests.

## [1.10.8] — 2026-08-20

### Added — Deploy refuses to ship a binding that will break

A method with no term id binds by NAME, and a rename in PDC then detaches it
silently — drift will not notice, because the contract and the catalog still
agree about the weak binding. Field history: the run of 2026-08-19 deployed 115
methods of which **40 bound by name**, because Reconcile's applied ids live in
memory and a restart between the two steps discarded them. Nothing downstream
said a word.

Deploy is the last moment the app can see it, so it stops there: **409** naming
the terms, why the ids went missing ("Reconcile, Apply and deploy in the SAME
session"), and how to proceed anyway. The **dry run is exempt** — it writes
nothing and is precisely how a steward should find this, so it reports
`name_binding` in the plan instead of refusing. The Deploy page offers both
routes where the refusal appears: *Reconcile first*, or *Deploy anyway, with
weak bindings* behind a confirm that spells out the consequence.

### Added — the identification read-back: did the rules actually fire?

`POST /api/pdc/identified` reads the columns of named tables and judges each
against the Registry: **expected_tagged**, **expected_missing**, **unexpected**,
**untouched**. `expected_missing` is the one worth having — a method that
deployed cleanly and then never fired is invisible in every other view this app
offers. Surfaced on the Report page.

Columns are located by **parentIds**, not by name. The first cut filtered COLUMN
entities by the table's name, which can only ever return nothing, and duly
reported "0 columns" for two tables that plainly have them. Pinned by
client-level tests, because the API tests stub the lookup and cannot catch it.

### Added — read one entity back, whole

`POST /api/pdc/entity` returns everything PDC holds on an entity (by id, or by
name), with `features` **verbatim** — a rating is not flattened to a number on
the way out, because the shape is often the answer. Written to settle "the write
said 200 and the catalog disagrees" without leaving the app; it immediately
proved the Glossary's table ratings omit the `users` map PDC needs.

### Added — quiet the catalog: disable the built-ins

`POST /api/pdc/builtins` counts, disables or restores PDC's shipped patterns and
dictionaries (137 on the lab: 95 dictionaries, 42 patterns). PDC ships them
enabled, so any identification started outside this app classifies against
shapes induced from somebody else's data — the drift a custom-only programme
exists to prevent. Dry run by default; never touches a custom method; reversible
with the same call. Card on the Reconcile page.

### Added — choose an identification scope instead of pasting one

`POST /api/pdc/entities` finds catalog entities by name, and the Deploy page
gained a table picker. The scope field previously wanted raw entity ids, which
meant leaving the app to copy a uuid — and a job that is tedious to scope ends
up unscoped.

### Fixed — two fixtures that were quietly wrong

`filter_entities` was never stubbed, so one test made real network calls, and
`test_needs_a_session` omitted `fake_pdc` and spent ten seconds failing to
resolve a hostname. The suite was doing that on every run. 85 tests, 1.7s.

### Changed — the UI explains itself

- **Workflow map** on Load, ported class-for-class from the Glossary's
  `WorkflowDiagram`: five clickable stages, the Registry arriving from the
  Glossary, the verdict leaving, Report on a dotted edge because it is a read
  and not a step. Each stage carries a one-line hover and a paragraph below.
- **The Registry contract diagram was redrawn** at 880×300 on three reserved
  bands ("bit squashed and needs more details") — arrow labels no longer sit on
  their arrows and the Drift return path no longer crosses the stage text.
- **Author explains what to do**: set the prefix (it is the scope Deploy, Drift
  and Retire all work in), preview, read **Bound** and **Evidence** first, fix
  what they reveal glossary-side, then download the zip or deploy. Plus a column
  glossary.
- **The Signature column disappears when it can only say "—"**, which is every
  row on an estate whose scan carries no position signatures. Conditional, not
  deleted: it returns the day one arrives.
- **Explainers lead both pages**, the Load summary sits above the session card,
  and the registry-row delete is the Glossary's ghost-button **✕**.

## [1.10.7] — 2026-08-19

### Fixed — the black stays in the art; the page body goes back to white

1.10.6's `MUI_BGCOLOR`/`MUI_TEXTCOLOR` painted the ENTIRE welcome/finish
dialog black — checkboxes and all — which read as a broken dialog rather
than brand (field: "the non icon side needs to be white"). The colour
defines are gone: the black now lives only where the art puts it — the
header band and the welcome sidebar bitmaps — and every page body follows
Windows' standard dialog colours again.

## [1.10.6] — 2026-08-19

### Changed — the swirl retires: Pentaho, capital P, white on black

The approved 2026 rebrand, ported from the Glossary Generator (1.38.28) so the
whole suite matches. Branding verified against the live pentaho.com and
user-approved from rendered previews:

- **App icon**: black tile, white capital P, short brand-red accent bar, the
  blue shield-check badge kept (a word is mush at 24 px; the badge is what
  tells the suite's taskbar pins apart). Full Tauri icon set regenerated.
- **Installer art**: NSIS header and welcome sidebar go black — white
  "Pentaho" wordmark, red accent bar, the P-tile with the shield badge on the
  sidebar.
- **Splash**: black field with a faint red floor-glow, white Pentaho wordmark
  over "Policy Generator", and the animated red bar inherits the swirl's
  alive-signal job — draws in on launch, breathes faster while more startup
  checks remain.

### Changed — the session comes before the Registry, and ✕ means delete

Both field-caught in the same pass.

- **Connect to PDC moved above Load a Classification Registry.** Every stage
  after Author reads the live catalog, so establishing the session is the first
  act on the page, not a card underneath the table you already used.
- **The registry-row delete is now the Glossary's `✕`** on a ghost button
  (`HomePage`'s saved-glossary and version rows), replacing the bin emoji — one
  habit across both apps. Only the hover tint is app-local: a destructive
  control should say so before it is clicked.

### Changed — the installer wears the suite's black

The uninstall dialog was still showing the retired red-swirl header, because
the black NSIS art (rebrand `ff44272`) reached the installer while the
uninstaller kept the default. `MUI_HEADERIMAGE_UNBITMAP` now points at the same
bitmap, and `MUI_BGCOLOR` / `MUI_TEXTCOLOR` paint the header band and the
Welcome/Finish pages black with white text; the progress log runs white on
black. MUI paints only those surfaces from its colour defines — the inner page
bodies still follow Windows' dialog colours, which would need per-control
`SetCtlColors` work to change.

## [1.10.5] — 2026-08-18

### Added — Report: one account of the whole pipeline

`ReportPage` compiles the contract, the authored set and the live catalog into a
single read: concepts and resolved ids, methods by **evidence** (profiled /
recognised / curated / name-anchored, each with what it means), the concepts
that were NOT authored grouped by reason, and the drift verdicts. A verdict line
says whether deployed and governed agree — and says "unknown, no session"
rather than implying agreement when it cannot check. **Export standalone HTML**
writes the whole thing as one self-contained file.

It is a sidebar page, not a sixth numbered stage: the workflow is five stages
and a report is something you read at any point.

### Added — delete a Registry from the Load page

`DELETE /api/registries?path=` removes one discovered Registry file, hard-scoped
to paths `discover_registries()` returned, so a stray path can never make it a
delete-anything endpoint. A row-level control with an explicit confirm; the
loaded Registry stays loaded when its file goes, because the working copy lives
in memory and may carry reconciled ids that exist nowhere else.

The listing was hardened in the same pass: a registries directory is shared with
the Glossary app, so a file can vanish between the glob and the stat — the
listing now skips what is already gone instead of raising over it.

### Changed — Reconcile stops asking for a connection and starts showing progress

The connect card belongs to Load (1.10.3), so Reconcile no longer carries a
second copy. In its place: a line naming the session it is working against with
the token's remaining life, or, when there is none, the way back to Load. The
batched reconcile now draws a real progress bar with a live line — "reconciling
50 of 142 (35%)", plus verified / resolved / mismatch / missing so far — and the
bar stays put when it finishes instead of vanishing.

### Changed — the handoff diagram carries the contract's contents

It was a 560x92 strip that could only name four boxes ("bit squashed and needs
more details"). Now 880x300, with the Registry's actual payload spelled out
(term + minted id, governed tags, sensitivity/category/sources, detection seeds
labelled by evidence, detection_intent), this app's three verbs against it, and
the dashed return path showing Drift reading PDC back. 67 tests.

## [1.10.4] — 2026-08-18

### Fixed — the condition variable that cost 81 patterns

Live-bisected against the lab after a 115-method deploy landed 34. A single
name-anchored rule, alone in its own zip, was rejected:

    java.lang.IllegalStateException: [columnCardinality] variable present in
    rule.condition is not valid
      at PatternManagerHelperKt.isValidCondition(PatternManagerHelper.kt:140)
      at PatternImporter.processJsonFile(PatternImporter.kt:95)
      at PatternImporter.processZipFile(PatternImporter.kt:161)

Two lessons, one line of code:

- **`columnCardinality` is legal in a Dictionary condition and illegal in a
  DataPattern one.** The clause was copied from PDC's shipped "Personal Data
  Identifier" template — a dictionary — when name-anchored rules were added in
  1.10.1. Those rules now gate on `confidenceScore >= 0.7` alone. The
  constant-column guard is simply not available to patterns; the name-AND-shape
  conjunction (0.5/0.5 against a 0.7 gate) is what keeps the rule honest.
- **Validation is per file, but the failure is per archive.** The exception
  escapes `processZipFile`, so the importer abandons every remaining file. Rule
  8 of 88 was name-anchored; patterns 8-88 never got read, including profiled
  ones that were perfectly valid.

### Added — the deploy stage reports what the worker said

`worker_status()` returns the whole `pipeline` payload rather than
`metadata.status` alone, and each Deploy worker row carries a `report`. PDC
finishes an import worker that rejected every file: status `COMPLETED`,
statistics `FAILED 1 / TOTAL 1`. Reading one field made a total failure look
like a success, and the app inferred the truth only by absence from a listing
that was itself capped (see 1.10.2). 65 tests.

## [1.10.3] — 2026-08-18

### Fixed — the connection was locked behind a page you could not open

Field-caught: "on the Load page could define a connection to PDC.. cant get to
the Reconcile page." Connecting is a setup act, not a reconcile act, but the
form only existed on Reconcile — and Reconcile is gated on a loaded Registry.
Restart the server (or just refresh) and the session was gone with no reachable
way to make a new one.

- **`components/PdcConnect.jsx`**: the session card, extracted from
  ReconcilePage and now rendered on **Load** as well. One component, one piece
  of App state — connecting in either place lights up the whole workflow.
- **The workflow adopts server state on boot.** The Registry and the PDC
  session live in the backend process, but the UI only learned about them by
  performing the action itself, so a refresh showed an empty workflow with
  every step past Load greyed out. App now reads `/api/summary` and
  `/api/pdc/status` at startup and adopts what is already there.

## [1.10.2] — 2026-08-18

### Fixed — the method listing is paged (it was blind past 100 rows)

Found by deploying 115 methods to the lab and being unable to say how many
landed. PDC's `DictionariesMany` / `DataPatternsMany` apply a server-side
default ceiling of 100 rows to a query that asks for no limit, and return an
arbitrary page rather than an error. `list_methods` then filtered by prefix in
Python — over that page. With 95 built-in dictionaries already in the catalog,
27 imported ones could only ever appear as 5.

Everything that decides what is or is not deployed reads through this one
call: deploy's post-import verification, the drift comparison, and the scoped
retire. The retire is the sharp end — it can only remove what it can see, so
the app could not reliably clean up its own deployment.

- `pdc._list_all()` pages each collection with `limit` / `skip` and stops on an
  EMPTY page, never a short one: a server that caps `limit` below what we ask
  returns a short page with more rows waiting, and `skip` advances by what
  arrived rather than what was requested.
- Two guards: a page cap, and a repeat-id check so a server that ignores
  `skip` is taken once instead of paged forever.
- A schema without `limit`/`skip` falls back to the old one-shot read rather
  than failing — it under-reports, which is the bug, so the fallback is
  narrow: only an argument error triggers it, any other GraphQL error raises.
- The prefix filter now runs over the complete collection.

64 tests.

## [1.10.1] — 2026-08-18

### Added — name-anchored seeds, and an Evidence column that says so

The Glossary's Registry (1.38.24) now carries a class of seed it used to drop:
the steward's **Auto flip** on a concept whose values carry no identifying
shape — a date, a bounded measure like pH or Lead ppb. Such a seed arrives
marked `identity: "column_name"`, and this app authors it differently:

- **The blend rebalances to name 0.5 + regex 0.5**, with the condition
  `confidenceScore >= 0.7 AND columnCardinality > 5`. Neither half clears the
  gate alone, so the rule is a strict name-AND-shape conjunction — under the
  stock 0.3/0.3/0.4 weights the same rule would either never fire or, trusting
  the shape alone, tag every numeric column in the estate. The cardinality
  guard is the one PDC's own shipped template uses: a constant column cannot
  satisfy a sanity shape. `metadataHints.aliases[].score` follows the name
  weight, so the hint and the confidence formula never tell PDC two different
  stories.
- **A profile signature rides such a rule at weight 0** — informative, inert.
  A flipped date does carry a `dddd-dd-dd` signature and dropping it would lose
  evidence PDC's own screens show.
- **Evidence column** on both Author tables (and `evidence` on every
  `/api/preview` row): profiled / recognised / curated / name-anchored, each
  with the one-line reason it is what it is. 88 authored methods of which 67
  rest on a column name is a fact a reviewer must be able to see without
  opening the JSON.

Profiled seeds are untouched — same weights, same condition, same envelope
verified against live PDC 11 in 1.8.0. 57 tests.

## [1.10.0] — 2026-08-08

### Added — Windows desktop installer (Tauri + vendored Python)

The Policy Generator now ships as a Windows `.exe`, packaged exactly like the
Glossary Generator and Catalog Insights: a `desktop/` Tauri shell that starts
the existing FastAPI server on a free port and points a webview at it — one
UI, served the same way in browser and desktop.

- **`desktop/` shell**: live-log splash driven by real uvicorn signals, a
  failure panel (retry in place / copy / save report / email support, plus
  local-model suggestions when the machine happens to run Ollama), a
  kill-on-close job object so a crashed shell never leaks uvicorn, and a
  vendored Python embeddable runtime (fastapi, uvicorn, python-multipart —
  nothing to install on the laptop). NSIS components page: Full (app +
  environment check) / Minimal (app only); silent flag `/S /NoCheck`.
  `provisioning\check-environment.ps1` reports rather than blocks and knows
  the PDC bare-IP vhost trap and the self-signed-vs-unreachable distinction.
  Code signing wired and off (`POLICY_SIGN_THUMBPRINT` or the suite-wide
  `PDCG_SIGN_THUMBPRINT`).
- **Registry discovery covers the packaged Glossary app.**
  `discover_registries()` now also looks in
  `%APPDATA%\com.pentaho.pdc-glossary\registries` (the Glossary desktop
  install's per-user state) and `%APPDATA%\PDC-Glossary\registries` (its
  unset-variable fallback), so the two Windows installers hand off on one
  laptop with nothing configured. The splash reports how many Registry files
  it can see before the app even opens. Covered by a new engine test.
- No state-dir plumbing was needed, and that is by design: the app's one
  write (`seed-request.json`) lands beside the loaded Registry, and PDC
  credentials never persist — so the packaged build under a read-only
  Program Files changes nothing about how the app behaves.

## [1.9.0] — 2026-07-18

### Added — the no-seed loop closes

A seedless, identifiable concept was the one state the contract couldn't
settle: either a seed is still missing, or no detectable shape exists and
the steward should say so. Both directions are now files in the shared
`registries/` folder — no runtime coupling between the apps.

- **Contract: optional `detection_intent` per concept**
  (`classification-registry/1`, backward compatible — absent = unknown).
  `"seeded"` = seeds exist; `"mapping_only"` = the steward decided no
  detectable shape exists, so the Glossary app's Apply step is the whole
  governance story. Documented in docs/CONTRACT.md (field table + a new
  "The no-seed loop" section).
- **Author page: "Mapping-only by steward decision" bucket.** Concepts with
  `detection_intent: "mapping_only"` leave the amber "Needs a detection
  seed" warning for a calm, informational bucket (steward intent beats the
  name heuristics). They are never authored — even if seeds linger — and
  `registry.seeded_concepts` no longer counts them as authorable.
- **⇪ Export seed request** (`POST /api/seed-request`). For the terms still
  in the amber bucket, one click writes `seed-request.json`
  (`{requested_at, registry_file, terms: [{name, reason: "no_seed"}]}`)
  into the same directory the loaded Registry came from, so the Glossary
  app can discover the ask. Requires a path-loaded Registry (an uploaded
  file has no home directory to write back into). Engine stays stdlib-only
  (`registry.write_seed_request`).
- **Drift: mapping_only is exempt from `missing` verdicts** by
  construction — author skips the concept, so drift never expects a method
  it must not have. A deployed method for one still surfaces as `orphaned`.

### Fixed — PDC session lifecycle: transparent re-auth on 401

Keycloak tokens live minutes; a steward's session lives hours. "List
methods" (and any later PDC call) could report "PDC session expired —
connect again" while the header still showed ✓ connected. Every
PDC-touching endpoint (methods list, retire, reconcile, deploy, drift,
identify) now rides through expiry: on a 401 the backend re-authenticates
once with the connect-time credentials — held in process memory only,
never persisted, never echoed back — swaps in the fresh token for the whole
session, and retries. Token-only sessions (pasted bearer) can't self-heal
and still get the honest 401; `/api/pdc/status` reports `renewable` so the
UI can tell the two apart.

### Fixed — layout
- Load page, discovered-registries table: fixed column plan (colgroup, the
  Glossary Home treatment) with the numeric Concepts value right-aligned
  directly under its right-aligned header.
- "✓ by id" / "⚠ by name" badges no longer squash/wrap in narrow cells
  (`.badge` gets `white-space: nowrap` + slightly more padding).
- Reconcile page: the verified/resolved/mismatch/missing summary chips get
  their own row with clear air below, so the results table's scroll area no
  longer crowds right under the badges.

### Tests
47 offline tests (was 35): detection_intent normalisation, mapping_only
authorable-set/author-skip/drift-exemption, seed-request schema + endpoint
(path-loaded, uploaded, empty ask), preview bucketing, and the re-auth
retry path (401-then-200, credential vs token-only sessions).

## [1.8.1] — 2026-07-17

### Changed — docs sync
Docs-only release. README's "Learn as you go" now covers the per-page
collapsed explainer cards (Registry contract on Load, skipped-groups legend
on Author, what Deploy does, reading the Drift verdicts) and the sidebar
footer's live PDC session status. INSTALL.md caught up with 1.8.0: the test
count is 35 (was 20), the engine listing includes `drift.py`, and the
"what you will have" list notes the Deploy stage as the programmatic
alternative to the manual UI import. No code changes.

## [1.8.0] — 2026-07-17

### Added — Deploy + Drift-check: the lifecycle is complete

The app's five-stage lifecycle (Load → Author → Reconcile → Deploy →
Drift-check) is now fully implemented; the last two stages were built against
a live PDC 11.0.0 and verified end-to-end (import → verify → bind → retire).

- **Deploy** (`POST /api/pdc/deploy`, DeployPage in the UI). PDC 11 has no
  public import API for Data Identification methods, so the UI's own path
  was discovered live: a multipart **`POST /api/importWorkerFiles`** (fields
  `type` = `DATA_PATTERNS_IMPORTER` | `DICTIONARY_IMPORTER`, `fileName`,
  `file`) — found by reading the SPA bundle (`/client/App.js`) after GraphQL
  suggestion probing showed no import mutation (`DictionariesCreateOne` /
  `DataPatternsCreateOne` exist, but the dictionary input carries no values
  field — the CSV only travels in the zip). This app's author-stage zips
  import **as-is** (same export layout), deterministic `_id`s preserved.
  The response is a worker record; progress is polled over the `WorkersById`
  GraphQL query (`pipeline.metadata.status`: RUNNING → COMPLETED/FAILED).
  Deploy then re-lists the prefixed set to verify every method landed, and
  **re-stamps the Registry's minted term ids** via `DictionariesUpdateById` /
  `DataPatternsUpdateById` — necessary because the importer rewrites an id
  it cannot resolve to the term name. `dry_run: true` returns the
  create/update plan without touching PDC. Deploy is always prefix-scoped,
  so the Reconcile page's scoped retire can clean up exactly what it
  imported.
- **Term-binding fix in Author** (the bug Deploy discovery surfaced): the
  authored envelopes carried `assignBusinessTerm`, which is **not** in PDC
  11's live schema — the importer silently dropped it, so the binding never
  reached PDC. The live field is **`applyBusinessTerms`** `[{name, id}]`
  (verified round-trip); author.py now emits it.
- **Optional bulk identification** (`POST /api/pdc/identify`): triggers one
  `DATA_IDENTIFICATION` job over **`POST /api/start-job`** (`{name, type:
  START, data: {scope, dictionaryIds, dataPatternIds}}` — the exact payload
  PDC's UI sends, read from the SPA bundle). An explicit entity-id scope is
  required; never catalog-wide.
- **Drift-check** (`POST /api/pdc/drift`, DriftPage in the UI, engine in the
  new `policy_generator/drift.py`). Every deployed method under the prefix
  is read in full (`DictionariesById` / `DataPatternsById`; `regexMatch`,
  `metadataHints` and `rules[].actions` are JSON scalars on the live schema)
  and compared against the Registry: governed tags vs the allow-list, term
  binding (name + id), content regex and profile signature vs the seeds,
  dictionary row counts (PDC does not expose dictionary values over GraphQL,
  so the count is the honest proxy), and enabled state. Verdict per method:
  **clean / drifted / orphaned / missing**, rendered reconcile-style with
  the exact findings.
- **UI**: the canonical shell gains Deploy (upload-tray icon) and Drift
  (scales icon) in the WORKFLOW section; the stepper runs Load → Author →
  Reconcile → Deploy → Drift. The PDC session now lives in App state so the
  gates hold across pages: Deploy needs a Registry + PDC session + at least
  one reconciled term id; Drift needs a Registry + PDC session. New
  `GET /api/pdc/status` backs the gating.
- **Tests**: 20 → 35. Mocked-PDC coverage for deploy (zip payload shape,
  dry-run never uploads, prefix guard, verify + selective id binding),
  identify (scope required, built-ins excluded), the drift endpoint, and a
  drift-engine suite (clean echo, missing, orphaned, off-vocabulary tags,
  importer-rewritten term ids, regex/row-count edits, disabled methods).
- **UI polish**: collapsed-by-default explainer cards in the Glossary app's
  details/summary pattern — the Registry contract (Load, with an inline-SVG
  two-app handoff graphic: Glossary Generator → Registry → Policy Generator →
  Data Identification in PDC), the skipped-groups legend (Author), what
  Deploy does (Deploy), and reading the verdicts (Drift). The sidebar footer
  now shows a live PDC session status (green dot + user when connected,
  matching the Insights shell), and the OpenAPI title is "Policy Generator"
  for tab-title consistency with the UI.

### Changed — suite shell uniformity

Suite shell uniformity — sidebar restructured to the shared shell (sections,
icons, footer status, theme select), light default theme. The masthead layout
is replaced by the canonical PDC suite shell from Catalog Insights: brand
block (rounded app mark + two-line name + version chip that still opens the
changelog), a WORKFLOW / CONFIGURE sectioned sidebar with inline SVG icons
(Load / Author / Reconcile / Settings), a breadcrumb topbar, and a sidebar
footer holding the API-docs link and the theme select. The stepper, pages and
API are unchanged.

## [1.7.2] — 2026-07-17

### Changed — Windows-first install docs
Docs-only release. README's Install & run and INSTALL.md Parts A/B now lead
with the Windows 11 host path (the standard topology: apps on the host via
PDC-Scenarios' `install-pdc-demo.ps1` into `C:\PDC-Demo`, lab + PDC on the
Ubuntu VM), with the lab-VM and manual paths second. No code changes.

## [1.7.1] — 2026-07-17

### Fixed — post-port sweep (VM installer, docs, comments)

- **`install-pdc-demo.sh` Verify step** still ran `python -m
  policy_generator.selftest` — removed in 1.7.0 — so every install warned
  "Selftest failed". It now runs a dependency-free CLI smoke test
  (`python3 -m policy_generator.cli --help`) that works on the sparse VM
  checkout with no venv.
- **`install-pdc-demo.sh` sparse checkout** pulled only `policy_generator/`,
  so the React `frontend/` never reached the VM and installs had no web UI.
  The sparse set now includes `frontend` (existing clones gain it on the next
  update run), and when `npm` is available the script builds the UI
  (`npm install && npm run build`); without npm it warns that the web UI
  needs Node 18+ to build and the app serves API + `/docs` only.
- Doc/comment drift from the 1.7.0 port: `docs/INSTALL.md` front matter said
  "App 1.4.x" (now 1.7.x); the `docs/tools/build-docx.py` subtitle said
  "web UI, CLI and selftest" (now "pytest suite"); `run.ps1` header comments
  still described the Flask-era `python app.py` launch (it starts
  `uvicorn policy_generator.api:app`).

## [1.7.0] — 2026-07-17

### Changed — React + FastAPI port (architectural)

- **Web layer rebuilt**: Flask + a single 927-line server-rendered template becomes
  **FastAPI** (`policy_generator/api.py`) + a **React (Vite) frontend** on the same
  design system as Migration Copilot — guided stepper (Load → Author → Reconcile),
  four color themes, changelog popup, Settings view. The `/api/*` contract is
  preserved route-for-route; the engine (`registry` / `author` / `pdc` / `cli`)
  is unchanged.
- **Auto-generated API docs** at `/docs` (Swagger), from typed Pydantic models —
  every endpoint documented, with a back-link to the app.
- **Tests**: the selftest suites are ported to **pytest** (engine invariants,
  API flows with mocked PDC, batched reconcile, scoped retire) plus a
  docs-consistency test that fails the build when version markers drift —
  which is exactly what had happened (VERSION said 1.6.0, README said 1.5.4).
- **Packaging**: `pyproject.toml`; requirements move from Flask to
  fastapi/uvicorn/python-multipart (the engine and CLI remain stdlib-only);
  launchers (`run.sh` / `run.ps1`) now start uvicorn and warn when the UI
  bundle isn't built; GitHub Actions CI (pytest + frontend build).
- **Removed**: `app.py` (Flask), `templates/`, `static/`, `selftest.py` —
  superseded by the above; history preserved in git.
- Docs: CHANGELOG moved to the repo root; `VERSION.md` added.

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

## [1.6.0] — 2026-07-15

### Added

- **Retire imported set** on the Reconcile page — deletes the app's authored
  Data Identification methods (dictionaries *and* patterns) over PDC's GraphQL
  endpoint, filling a real product gap: **PDC 11.0's method list has no Delete**
  (only View/Edit). Scoped to a name prefix so it can only ever touch your set;
  built-ins are refused outright even if one carries the prefix. **Preview
  matches** lists first (read-only); **Retire set** deletes after a
  confirmation, with a per-method result table.
- PDC client (`pdc.py`): `graphql()`, `list_methods(prefix=…)`, and
  `remove_method(kind, _id)`. Data Identification is backed by a
  graphql-compose-mongoose Apollo endpoint at `{pdc}/graphql`, authenticated by
  the same Keycloak bearer token as the REST API. Field names
  (`DictionariesMany`/`DataPatternsMany`, `DictionariesRemoveById`/
  `DataPatternsRemoveById`) were **confirmed live against PDC 11.0.0** by
  discovery through Apollo's validation-error suggestions (introspection is
  disabled in production), then exercised end-to-end deleting the CSCU set.
- Endpoints `POST /api/pdc/methods` (scoped list) and `POST /api/pdc/retire`
  (scoped delete, built-ins refused, optional `ids` allow-list). Selftest grows
  to 31 checks (transport-stubbed coverage of list/remove/kind-guard).

### Note

- Deterministic UUID5 ids make a re-import an **upsert**, so a clean re-run
  rarely needs retire — reach for it when a term leaves the glossary and its
  orphaned method would otherwise linger.

## [1.5.4] — 2026-07-15

### Changed

- Documented a live-confirmed PDC editor quirk in the import hoodcard (and
  the CSCU workshop): the edit form does not hydrate an imported rule's
  JsonLogic condition (View → Rules shows it; it evaluates) — hand-editing
  an imported method risks saving an emptied condition. The governed change
  path is adjust-and-re-import (deterministic ids = clean updates).

## [1.5.3] — 2026-07-15

### Fixed — rules never fired on demo-scale tables (minSamples)

First live Data Identification run: methods imported, term bound, but **no
tags stamped**. Cause: copying the built-in envelopes verbatim brought
`minSamples: 200` along — a rule doesn't evaluate until it has 200 sampled
values, and the lab's tables are tiny (13 members). Now `minSamples: 1`
(rule + pattern envelope), so methods fire on demo data; stewards can raise
it in PDC for production volumes.

## [1.5.2] — 2026-07-15

### Fixed — pattern import validation ("No Tag found in Rule")

PDC's import validator walks **every** action object and requires a tag in
each; our separate `{assignBusinessTerm}` action object had none, so
`PatternImporter.validateJsonForNewPattern` rejected the file (live worker
log from the lab). Two changes:

- **One action object per rule**: `applyTags` and `assignBusinessTerm` now
  ride in the same object, matching how built-ins structure actions.
- **A concept whose tags all fall to the allow-list filter is skipped**
  (with the reason) instead of authored — an untaggable method can neither
  pass validation nor govern anything; fix its tags glossary-side.

Selftest 26 checks.

## [1.5.1] — 2026-07-15

### Changed

- The "What these groups mean — and what to do about each" explainer now
  sits **above** the color-coded skipped groups (read the legend first,
  then the lists), still collapsed by default.

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
