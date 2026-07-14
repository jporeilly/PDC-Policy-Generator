# The Classification Registry contract (`classification-registry/1`)

Written by the **Glossary Generator** at Generate time
(`glossary_generator/registries/registry.<glossary-uuid>.json`), read by
**this app**. One file per glossary; regenerated on every export (export
time = latest reviewed state). The Glossary app's **Resolve Term IDs** step
backfills `term_id` / `glossary_id` after the glossary is imported into PDC.

The whole lifecycle of one Registry file — who writes, who reads, and when
the ids arrive:

```mermaid
%%{init: {'theme':'base','themeVariables':{'fontFamily':'Segoe UI, sans-serif','fontSize':'13px','actorBkg':'#EEF6FA','actorBorder':'#1C7293','actorTextColor':'#0A3D52','actorLineColor':'#CFE3EC','signalColor':'#1C7293','signalTextColor':'#22333B','noteBkgColor':'#FFF7E0','noteBorderColor':'#C9A227','noteTextColor':'#7A5A00','activationBkgColor':'#DBEEF3','activationBorderColor':'#1C7293','sequenceNumberColor':'#FFFFFF'}}}%%
sequenceDiagram
    autonumber
    participant GG as Glossary Generator<br/>:5000
    participant REG as Classification Registry<br/>registry.*.json
    participant PDC as PDC 11
    participant PG as Policy Generator<br/>:5001

    rect rgb(247,251,253)
        note over GG,REG: Generate — the contract is written
        GG->>REG: one governed row per kept, reviewed concept<br/>(term_id: null — nothing minted yet)
    end
    rect rgb(238,246,250)
        note over GG,PDC: Glossary import — PDC mints the ids
        GG->>PDC: import glossary JSONL
        PDC-->>GG: minted term ids
        GG->>REG: Resolve Term IDs — backfill term_id / glossary_id
    end
    rect rgb(247,251,253)
        note over REG,PG: Author + Reconcile — the contract is read
        PG->>REG: auto-discover + load the newest Registry
        PG->>PG: author patterns + dictionaries<br/>(tags re-filtered against the allow-list)
        PG->>PDC: verify each term_id (three-path lookup)
        PG->>REG: stamp verified ids — export a reconciled copy
    end
    note over PDC,PG: roadmap — deploy + drift-check
    PG--)PDC: import methods over public API v3, trigger DATA_IDENTIFICATION
    PDC--)PG: live tag facet, compared against tag_vocabulary
    PG--)REG: write back the method binding (the reserved field)
```

## Envelope

| Field | Meaning |
| --- | --- |
| `schema` | always `classification-registry/1` |
| `glossary` / `glossary_id` | the glossary name and its deterministic UUID5 (null until resolved) |
| `concepts[]` | one entry per kept, reviewed term — see below |
| `tag_vocabulary` | the governed tag allow-list (lower-case), per-tag sensitivity floors, canonical terms with aliases, the pack domain — the drift boundary both apps share |
| `governance_audit` | compact who-approved-what summary from the app's audit trail (provenance travels with the contract) |

## Concept fields

| Field | Meaning | Used by this app for |
| --- | --- | --- |
| `concept` | stable slug of the term | filenames, matching |
| `term_name` | the governed business term | `assignBusinessTerm`, name binding |
| `term_id` | PDC's minted term id (null until glossary import + Resolve) | id binding (reconcile) |
| `sensitivity` | LOW / MEDIUM / HIGH, floor-lifted | drift checks vs tag floors |
| `tags` | governed, lower-case | rule `applyTags` (re-filtered against `tag_vocabulary.allow_list` at authoring) |
| `off_vocabulary_tags` | tags that escaped the allow-list | authoring refuses them; drift flags them |
| `category` | glossary category | rule `category` grouping |
| `definition` | the steward's reviewed definition | context in review output |
| `detect[]` | detection seeds: `{type: "pattern", regex, signature?, source}` or `{type: "dictionary", values[], source}`. `source: "profiled"` = induced from scanned data; `source: "curated"` = a vetted canonical shape or reference list from the domain pack's `curated_seeds` (profiled wins over curated for the same seed type) | **the authorable core** — one method per seed |
| `sources[]` | the physical columns/files the term maps to | column-name regex hints |
| `keys` | per-source `{pk, fk, ref}` facts | relationship context (identity vs join) |
| `method` | reserved: the deployed method binding this app writes back | reconcile/drift |

## The contract at a glance

```mermaid
%%{init: {'theme':'base','themeVariables':{'primaryColor':'#EEF6FA','primaryBorderColor':'#1C7293','primaryTextColor':'#22333B','lineColor':'#1C7293','fontFamily':'Segoe UI, sans-serif','fontSize':'13px','clusterBkg':'#F7FBFD','clusterBorder':'#CFE3EC','edgeLabelBackground':'#FFFFFF'},'flowchart':{'curve':'basis','nodeSpacing':30,'rankSpacing':60}}}%%
flowchart LR
    subgraph FILE["registry.&lt;glossary-uuid&gt;.json &mdash; schema: classification-registry/1"]
        direction TB
        subgraph ENV["Envelope"]
            direction TB
            SCH["glossary &middot; glossary_id<br/><small>deterministic UUID5 &mdash; null until resolved</small>"]
            VOC["tag_vocabulary<br/><small>governed allow-list &middot; sensitivity floors &middot;<br/>canonical terms + aliases &middot; pack domain</small>"]
            AUD["governance_audit<br/><small>who approved what &mdash; provenance<br/>travels with the contract</small>"]
        end
        subgraph CON["concepts[ ] &mdash; one per kept, reviewed term"]
            direction TB
            IDF["concept &middot; term_name &middot; term_id<br/><small>identity + binding</small>"]
            GOVF["sensitivity &middot; tags &middot; off_vocabulary_tags &middot;<br/>category &middot; definition<br/><small>the governed facts</small>"]
            DET["detect[ ] &mdash; the authorable core<br/><small>pattern regex / dictionary values<br/>source: profiled | curated</small>"]
            SRC["sources[ ] + keys<br/><small>physical columns &middot; pk/fk facts</small>"]
            MET["method<br/><small>reserved &mdash; deploy write-back</small>"]
        end
    end
    METH["Data Patterns +<br/>Dictionaries<br/><small>one method per seed</small>"]
    DET == "Author" ==> METH
    VOC -. "re-filtered at authoring &mdash;<br/>off-vocabulary tags refused" .-> METH
    METH ==> PDC[("PDC Data<br/>Identification")]
    MET -. "drift-check (roadmap)" .- PDC

    classDef seed fill:#FFF7E0,stroke:#C9A227,color:#7A5A00
    classDef vocab fill:#DBEEF3,stroke:#1C7293,color:#0A3D52
    classDef roadmap fill:#F4F6F7,stroke:#9AA5AB,color:#5B6770,stroke-dasharray:4 3
    classDef method fill:#0A3D52,color:#fff,stroke:#0A3D52,stroke-width:2px
    classDef pdc fill:#DBEEF3,stroke:#065A82,color:#0A3D52,stroke-width:2px
    class DET seed
    class VOC vocab
    class MET roadmap
    class METH method
    class PDC pdc
```

## Guarantees the contract gives

- **Tags cannot drift**: rules only ever stamp tags from
  `tag_vocabulary.allow_list` (checked again at authoring), and the same
  allow-list drives the Glossary app's tagging — one vocabulary, two apps.
- **Deterministic ids**: `glossary_id` and term ids are UUID5s derived from
  names, the same ids the glossary JSONL carries — so bindings survive
  re-exports.
- **Evidence-grounded methods**: every regex/dictionary was induced from
  profiled data or comes from the pack's vetted `curated_seeds` (`source`
  says which), never guessed from names — the custom-only program's
  auditable replacement for PDC's built-ins.
