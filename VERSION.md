# Version

**1.7.1** — 2026-07-17

Fix release on the 1.7 line: VM installer verify + frontend, doc/comment
sweep. See [CHANGELOG.md](CHANGELOG.md) for history.
The runtime source of truth is `policy_generator/VERSION` (the API banner and
`python -m policy_generator --version` read it); a docs-consistency test keeps
every marker in agreement.
