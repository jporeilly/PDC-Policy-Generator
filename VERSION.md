# Version

**1.9.0** — 2026-07-18

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

Previously — **1.8.1** (2026-07-17):
docs-only release — README and INSTALL.md caught up with the shipped 1.8.0
Deploy + Drift lifecycle (explainer cards, footer PDC session status,
`drift.py` in the engine listing).

Previously — **1.8.0** (2026-07-17):
the lifecycle is complete: **Deploy** (programmatic import over PDC's
discovered import API, post-import term-id re-stamping, optional scoped
DATA_IDENTIFICATION job) and **Drift-check** (per-method clean / drifted /
orphaned / missing verdicts against the Registry) ship, both verified live
against PDC 11.0.0. See [CHANGELOG.md](CHANGELOG.md) for history.
The runtime source of truth is `policy_generator/VERSION` (the API banner and
`python -m policy_generator --version` read it); a docs-consistency test keeps
every marker in agreement.
