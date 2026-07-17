# Version

**1.8.1** — 2026-07-17

Docs-only release: README and INSTALL.md caught up with the shipped 1.8.0
Deploy + Drift lifecycle (explainer cards, footer PDC session status, the
35-test count, `drift.py` in the engine listing).

Previously — **1.8.0** (2026-07-17):
the lifecycle is complete: **Deploy** (programmatic import over PDC's
discovered import API, post-import term-id re-stamping, optional scoped
DATA_IDENTIFICATION job) and **Drift-check** (per-method clean / drifted /
orphaned / missing verdicts against the Registry) ship, both verified live
against PDC 11.0.0. See [CHANGELOG.md](CHANGELOG.md) for history.
The runtime source of truth is `policy_generator/VERSION` (the API banner and
`python -m policy_generator --version` read it); a docs-consistency test keeps
every marker in agreement.
