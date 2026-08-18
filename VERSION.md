# Version

**1.10.1** — 2026-08-18

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
