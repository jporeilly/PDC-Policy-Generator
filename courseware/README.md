# Courseware — one workshop set per scenario

| Set | Scenario | Contents |
| --- | --- | --- |
| [`CSCU/`](CSCU/) | **Copper State Credit Union** — financial services | The Policy Generator app workshop: Registry → `info` → `author` → import into PDC → run Data Identification → verify the governed vocabulary landed |

Each workshop folder carries a markdown guide master (authoritative, with
`[SCREENSHOT]` markers for captures on that scenario's lab), a `.docx`
generated from it in the course design (`<set>/tools/build-docx.py`), and its
assets. The workshops assume the matching **Glossary Generator** set
([PDC-Glossary-Generator](https://github.com/jporeilly/PDC-Glossary-Generator)
`courseware/<ID>/`) has been completed first — that repo owns the scenario
data (`data_sources/<ID>/`), the shared lab stack, and Workshops 00–05; this
repo's sets pick up at the Registry hand-off.

Additional scenarios (RETAIL, HEALTH, MFG) plug in the same way: a
`courseware/<ID>/` set here beside the matching set in the Glossary repo,
authored against that scenario's Registry. They will be added as the
reconcile / deploy / drift-check stages ship.

*All scenario data is fictional and generated for training.*
