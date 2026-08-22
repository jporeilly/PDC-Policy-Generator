# Version

**1.10.14** — 2026-08-21

The Load overview now explains the five stages as tiles — numbered dot, title,
explanation and a Go-to button per stage, the Glossary Generator's Home
treatment — so the suite's two halves read the same way. Report stays
unnumbered: it is not a step but the account of the other five.

Previously — **1.10.9** (2026-08-20):

The day the pipeline was proven end to end on a live estate — and the four
silent failures that turned up on the way. A numeric threshold meant no Data
Pattern ever fired; a stale profile meant patterns matched against data that no
longer existed; a boolean column can never be content-matched at all; and one
induced shape backed eight concepts, so a free-text column was bound to all of
them. Each is fixed, each is guarded, and each guard says what will silently not
work BEFORE it does not work.

Previously — **1.10.8** (2026-08-20):

Deploy stops a binding that will break. A method with no term id binds by NAME,
and a rename in PDC then detaches it silently — drift cannot see it, because
the contract and the catalog agree about the weak binding. Deploy now refuses,
names the terms, and says why the ids went missing; the dry run reports instead.

Alongside it, the last mile of the pipeline arrives: **read-back**. What did
identification actually tag (`/api/pdc/identified`, judged against the Registry),
what does PDC hold on one entity (`/api/pdc/entity`, features verbatim), and a
switch to **disable the shipped built-ins** so a run means what it says.

Previously — **1.10.7** (2026-08-19):

Connect first, and delete with the same ✕ the Glossary uses. The PDC session
card now sits ABOVE the Registry list on Load — Reconcile, Deploy and Drift all
read the live catalog, so the session is the first thing to establish, not an
afterthought below the table. The registry-row delete drops the bin glyph for
the ghost-button ✕ of the Glossary's saved-glossary rows, so one habit works
across both apps. The installer and uninstaller are themed black with white
text on the header band and the Welcome/Finish pages, and the uninstaller is
explicitly given the same black header art.

Previously — **1.10.5** (2026-08-18):

A Report page, registry housekeeping, and a Reconcile that shows its work. The
new **Report** reads the contract, the authored set and (when a session exists)
the live catalog into one account, exportable as standalone HTML. Registry files
can be **deleted** from the Load page, scoped to the files this app itself
discovered. The connect form now lives on Load alone, so **Reconcile** shows
which session it is working against and a progress bar with running tallies
instead of a silent button. The handoff diagram is drawn at a size that can
carry the contract's actual contents.

Previously — **1.10.4** (2026-08-18):

A DataPattern condition may not mention `columnCardinality`. PDC's importer
rejects the file outright — `IllegalStateException: [columnCardinality]
variable present in rule.condition is not valid` — and, because validation
runs per file inside `processZipFile`, the exception abandons the WHOLE
archive: one bad rule at position 8 cost 81 patterns. The guard was borrowed
from the shipped Personal Data Identifier template, which is a dictionary,
where the same variable is legal. Name-anchored rules now gate on
`confidenceScore >= 0.7` alone, and the deploy stage reports what the import
worker actually said instead of trusting its COMPLETED.

Previously — **1.10.3** (2026-08-18):

Connect from the Load page, and adopt the session the server already has. The
PDC connection form lived only on Reconcile — a page that stays locked until a
Registry is loaded — so a dropped session could leave no reachable way back in.
The same card now sits on Load, and the workflow adopts whatever the backend
already holds on boot, so a browser refresh no longer shows an empty workflow
in front of a fully loaded server.

Previously — **1.10.2** (2026-08-18):

The method listing is paged. PDC's `*Many` resolvers cap a limitless query at
100 rows and answer with an arbitrary page rather than an error, and every
question about what is deployed — deploy's own verification, drift, and the
scoped retire — reads through that one call. On a catalog holding 95 built-in
dictionaries, a 27-method import could only ever surface as 5, so a partial
deploy was indistinguishable from a failed one and retire could not see what
it was meant to clean up. `list_methods` now pages until a page comes back
empty and filters by prefix over the complete collection.

Previously — **1.10.1** (2026-08-18):

Name-anchored seeds. The Registry the Glossary Generator writes now carries the
steward's Auto flip on a concept whose values have no identifying shape — a
date, a bounded measure like pH or Lead ppb — as a pattern seed marked
`identity: "column_name"`. Authoring one with the stock weights would ship a
rule that either never fires or tags every numeric column in the estate, so
the blend rebalances to name 0.5 + regex 0.5 with PDC's own cardinality guard,
and the rule fires only when name AND shape agree. The Author tables gained an
**Evidence** column, because a name-anchored method is a weaker claim than a
profiled shape and a reviewer is entitled to see which is which.

Previously — **1.10.0** (2026-08-08):

Windows desktop installer. The app now ships as a `.exe` built from the new
`desktop/` Tauri shell — the same packaging as the Glossary Generator and
Catalog Insights: a vendored Python embeddable runtime (nothing to install),
a live-log splash with a retry/report failure panel, a kill-on-close job
object, and an NSIS components installer (Full = app + environment check;
silent `/S /NoCheck`). `discover_registries()` additionally searches the
packaged Glossary app's per-user state
(`%APPDATA%\com.pentaho.pdc-glossary\registries`), so the two installers hand
off on one laptop with nothing configured. No state-dir plumbing was needed:
the app's one write lands beside the loaded Registry, by design.

Previously — **1.9.0** (2026-07-18):
The no-seed loop closes. The `classification-registry/1` contract gains an
OPTIONAL per-concept `detection_intent` field (`"seeded"` | `"mapping_only"`;
absent = unknown — fully backward compatible): `mapping_only` records the
steward's explicit decision that no detectable shape exists, so the concept
leaves the Author page's amber "needs a seed" bucket for a calm
"Mapping-only by steward decision" one, is never authored, and is exempt
from drift's `missing` verdict. For the terms still waiting,
**⇪ Export seed request** (`POST /api/seed-request`) writes
`seed-request.json` beside the loaded Registry — the shared `registries/`
folder — for the Glossary app to discover. Plus two layout fixes (Load
table column alignment, Bound-badge nowrap).
