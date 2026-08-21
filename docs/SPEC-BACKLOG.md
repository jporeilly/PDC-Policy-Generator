# Spec backlog — pointer

The Policy Generator's outstanding spec items live with the Glossary
Generator's, in one file:

**`PDC-Glossary/docs/SPEC-BACKLOG-20260821.md`**

They were all found on the same walk — the Glossary → Policy pipeline run end
to end on the live Arizona Water estate on 2026-08-21 — and several only make
sense against each other, so they are kept together rather than split by repo.

The Policy-side items are:

| # | item |
|---|---|
| 5 | **Efficacy check** — does each deployed method still match any *data*? Drift reads the contract, re-profiling reads the data, and neither reads both. A method whose data moved underneath it reports clean and matches zero rows forever. |
| 6 | **Identification scope picker derived from the Registry** — the tables the deployed set can actually tag, with a count of how many methods can fire on each. Not a catalog browser. |
| 7 | **Patterns cannot score above their name hint** — an investigation, not yet a spec. On the AWC estate `regexScore` returned zero, so a pattern's ceiling was 0.09 against thresholds of 0.5. Mechanism unconfirmed; reproduce before implementing anything. |

Item 4 in that file concerns AI-proposed label vocabularies and explicitly does
**not** belong in `SPEC-policy-advisor.md`: labels are created and stamped by
the Glossary app, and the PG core stays deterministic (Advisor doctrine 3).
