# SPEC — Policy Advisor (AI-assisted standards from a written policy)

**Status:** speculative — approved for spec 2026-08-19 ("yes spec it as a PG
enhancement"), not yet scheduled. Target: **1.11.0** (new feature area).
**Origin:** the Workshop-6 field question — *"If we have a Policy, for example
Customer Data Privacy Policy, can an AI now determine which standard needs to
be applied and the column(s) to apply it to?"*

## The one-sentence design

The model decomposes a written **policy** into candidate **standards**; each
standard carries a **predicate over the governed vocabulary**, and the
**Registry resolves the predicate to columns deterministically** — AI proposes,
evidence decides, the steward approves.

## Doctrine (what keeps this auditable)

1. **The LLM never picks columns.** It proposes predicates whose atoms are
   restricted to the Registry's governed vocabulary (tags, categories, terms,
   label families). Grounding is a deterministic join — when the auditor asks
   "why these columns?", the answer is a query, not a model transcript.
2. **Proposals only.** Every suggestion is a card the steward accepts, edits,
   or dismisses — the pill discipline. Nothing reaches PDC or the Registry
   without an explicit accept. There is deliberately no Accept-all.
3. **The PG core stays deterministic.** The Advisor is an optional panel; the
   app must build, run, and pass its suite with no LLM configured. Ollama
   absent → the panel says so and the five stages are untouched.
4. **Counsel owns the numbers.** The Advisor drafts measurable *requirements*;
   retention periods, statutory citations and jurisdictional specifics are
   flagged `needs-counsel`, never invented. (Convergence with the queued
   **regulation packs** idea: packs are a curated obligations *source* with
   citations; the Advisor is a decomposition *source* from the user's own
   policy. Both emit the same standard+predicate shape and share the
   grounding layer below.)

## Pipeline

### 1 · Decompose (LLM, Ollama — the only model call)

Input: policy text (pasted, or a `.md`/`.txt`/`.docx` file; later: read from
the PDC policy-service once its read API is mapped). Plus the allowed
predicate vocabulary, injected into the prompt: tag names from the Registry's
governed set, category names, term names, label families/values.

Output (structured, validated):

```json
{"standards": [{
  "name": "Customer Marketing Consent Standard",
  "requirement": "Marketing communications must be suppressed for any
                  customer whose opt-out flag is set.",
  "rationale": "Policy clause: 'never for marketing where the customer
                has opted out'.",
  "predicate": {"any": [{"term": "Marketing Consent"}],
                 "all": [{"category": "Customer Management"}]},
  "flags": ["needs-counsel:none"]
}]}
```

Validation is deterministic and unforgiving: a predicate atom that names an
unknown tag/term/category/label **rejects that suggestion** with the reason
shown on its card ("references tag `consent-flag` — not in the governed set").
The model is re-prompted once with the rejection list; what still fails is
shown as rejected, never silently dropped.

### 2 · Ground (deterministic — no model)

Resolve each accepted-or-pending predicate against the Registry:

- atoms: `{"tag": t}` → terms carrying `t` in Suggested_Tags →
  their linked columns; `{"category": c}` → terms under `c`;
  `{"term": n}` → that term's columns; `{"label": {family, value}}` →
  columns stamped with that label (live session required).
- combinators: `all` (intersection), `any` (union), `not` (difference).

Output per standard: the column list with a **per-column why-chain**
("customers.email ← term *Email Address* ← tag `pii` ∧ category *Customer
Management*"). Zero columns is a legitimate result and renders as one
("predicate resolves to nothing on this estate — evidence gate, same rule as
generation: no evidence, no policy").

### 3 · Control-map (deterministic)

For each standard, match against the authored method set and the Registry's
DQ seeds: which existing pattern / dictionary / DQ expectation already
*measures* this requirement. Three outcomes per standard:

- **measured** — names the method(s); Deploy already covers it;
- **partially measured** — e.g. format is checked but suppression is not;
- **GAP** — no control exists; one click hands the standard's requirement to
  Author as a stub (the steward still authors the method deliberately).

### 4 · Review & emit

A suggestion card per standard: requirement · predicate (editable, re-grounds
live) · resolved columns with why-chains · control verdict · accept / edit /
dismiss. Accepted standards emit:

- **standards pack** — JSONL/CSV in the PDC Policy-page import shape
  (**open question #1**: whether that format carries a related-policy field
  or the link is made post-import in the relationship panel — being verified
  on the live rig; the emitter targets whichever is true);
- **association worksheet** — until a write API for associations is mapped,
  a checklist naming exactly what to attach where (asset → Policies tab),
  demo-honest and steward-executed;
- **gap hand-off** — stubs into Author for the missing controls.

## Placement & plumbing

- **UI:** a sidebar page like Report ("Advisor"), not a sixth numbered stage —
  the 5-stage lifecycle is settled. Requires a loaded Registry; a PDC session
  enriches (labels, live assignments) but is not required for steps 1–3.
- **API:** `POST /api/advisor/decompose` (policy text → suggestions, LLM),
  `POST /api/advisor/ground` (predicate → columns + why-chains, pure),
  `POST /api/advisor/controlmap` (standard → verdict, pure). Ground and
  controlmap are pure functions of Registry + method set — trivially testable.
- **LLM config:** reuse the suite's Ollama settings pattern (base URL +
  model), stored app-side; PG gains its first optional LLM dependency —
  isolate in `policy_generator/advisor_llm.py` so the core imports nothing
  from it.
- **Versioning:** 1.11.0. New tests: predicate validator (unknown-atom
  rejection), grounding determinism (fixture Registry → exact column sets),
  why-chain correctness, controlmap on the AWC fixture (account-number
  standard → measured by AWC_Account_Reference), core-runs-without-LLM.

## Worked example (the field question, on the live estate)

*Customer Data Privacy Policy* decomposes to ~3 standards; grounding on the
AWC Registry resolves: consent standard → `opted_out_marketing` (term link);
identifier-handling → `customer_name`, `email`, `phone`, `service_address`
(tag `pii` ∧ category *Customer Management*); the account-format standard is
recognised as already existing and **measured** by `AWC_Account_Reference` —
demonstrating all three control verdicts in one pass.

## Non-goals

- Authoring policy *documents* from nothing (input is a human-written policy).
- Writing standards/associations into PDC unattended (open question #2:
  whether the policy-service exposes create APIs at all).
- Regulatory numbers, citations, jurisdictions (regulation packs' territory).

## Open questions

1. PDC Policy-page bulk-import format: related-policy field or post-import
   linking? (Live check pending — morning of 2026-08-20.)
2. policy-service write APIs (create standard, create association) — route
   map not externally discoverable; revisit with a logged-in session's
   network trace.
3. Should label-family atoms require a live session, or should stamped labels
   be snapshotted into the Registry at generate time? (Leaning: snapshot —
   keeps grounding offline-reproducible.)
