import { useEffect, useState } from 'react'
import PdcConnect from '../components/PdcConnect.jsx'
import WorkflowDiagram from '../components/WorkflowDiagram.jsx'

// The five stages plus the Report read-out, tiled the same way the Glossary
// Generator's Home page explains its workflow. Report carries no number on
// purpose: it is not a stage, it is the account of the other five.
const STAGES = [
  { n: 1, id: 'load', title: 'Load', go: 'Load',
    text: 'Open the Classification Registry the Glossary Generator wrote at Generate. '
        + 'One governed row per concept: term, tags, sensitivity, detection seeds. '
        + 'Everything downstream reads this and nothing re-decides it.' },
  { n: 2, id: 'author', title: 'Author', go: 'Author',
    text: 'Turn each seeded row into an import-ready PDC method: a Data Pattern for a '
        + 'value shape, a Dictionary for a reference list. Deterministic and offline, '
        + 'so the same Registry always yields the same rules.' },
  { n: 3, id: 'reconcile', title: 'Reconcile', go: 'Reconcile',
    text: 'Look every term up in the live catalog and bind by id rather than by name, '
        + 'so a rename in PDC can never quietly unhook a method from its term. Needs a '
        + 'session; the ids it applies live in memory until you deploy or export.' },
  { n: 4, id: 'deploy', title: 'Deploy', go: 'Deploy',
    text: 'Import the authored set over PDC’s own import API, verify each method '
        + 'landed, and re-stamp the reconciled term ids afterwards. Everything stays '
        + 'under the name prefix, which is what lets Retire clean up exactly what this '
        + 'app created.' },
  { n: 5, id: 'drift', title: 'Drift', go: 'Drift',
    text: 'Read the catalog back and compare it against the Registry, method by method: '
        + 'clean, drifted (deployed but changed), missing (governed but absent), '
        + 'orphaned (deployed but no longer governed). This is the stage the whole '
        + 'pipeline exists for.' },
  { n: null, id: 'report', title: 'Report', go: 'Report',
    text: 'Not a step but a read: the contract, the authored set and the live catalog '
        + 'in one account, exportable as a standalone HTML file.' },
]

export default function LoadPage({ summary, onLoaded, pdc, onPdc, onNavigate }) {
  const [registries, setRegistries] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch('/api/registries')
      .then((r) => r.json())
      .then((b) => setRegistries(b.registries ?? []))
      .catch(() => {})
  }, [])

  async function deletePath(r) {
    // The row click loads; deleting must be an explicit, named act — the file
    // is the Glossary's output and there is no undo.
    if (!window.confirm(`Delete the Registry file ${r.file}?
` +
        `${r.glossary ?? 'unreadable'} · ${r.concepts ?? '—'} concept(s)

` +
        'The file is removed from disk. A Registry already loaded stays loaded ' +
        '(the working copy lives in memory, reconciled ids included).')) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/registries?path=${encodeURIComponent(r.path)}`, { method: 'DELETE' })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setRegistries(body.registries ?? [])
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function loadPath(path) {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(`/api/load?path=${encodeURIComponent(path)}`, { method: 'POST' })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      onLoaded(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function loadFile(file) {
    setBusy(true)
    setError(null)
    try {
      const form = new FormData()
      form.append('registry', file)
      const res = await fetch('/api/load', { method: 'POST', body: form })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      onLoaded(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <details className="card" open>
        <summary>The five stages — and what flows through them</summary>
        <p className="hint-line">
          Every box is a page: click one to go there. The chips are not this app's to
          make — the Registry arrives from the Glossary Generator, and the verdict is
          what Drift reports back about the live catalog.
        </p>
        <WorkflowDiagram onNavigate={onNavigate} />
        <div className="grid-2" style={{ marginTop: '.8rem' }}>
          {STAGES.map((s) => (
            <div className="tile" key={s.id}>
              <div className="bucket-title">
                <span className={`dot-num${s.n == null ? ' aside' : ''}`}>{s.n ?? '→'}</span> {s.title}
              </div>
              <p className="hint-line">{s.text}</p>
              {s.id === 'load'
                ? <span className="you-are-here">You are here</span>
                : <button className="ghost" onClick={() => onNavigate(s.id)}>Go to {s.go} →</button>}
            </div>
          ))}
        </div>
      </details>

      <RegistryContractExplainer />

      {summary && <SummaryCard summary={summary} />}

      <PdcConnect
        pdc={pdc}
        onPdc={onPdc}
        hint={'Connect first: Reconcile, Deploy and Drift all read the live catalog, and the '
              + 'session survives every page. The token lives in memory for this session only '
              + 'and the password is never stored.'}
      />

      <section className="card">
        <header>
          <h2>Load a Classification Registry</h2>
          <label className="ghost" style={{ cursor: 'pointer' }}>
            <input type="file" accept=".json" style={{ display: 'none' }}
                   onChange={(e) => e.target.files.length && loadFile(e.target.files[0])} />
            <span className="badge accent">⬆ Upload registry.json</span>
          </label>
        </header>
        <p className="hint-line">
          The Registry is the contract the Glossary Generator writes at export time
          (<code>classification-registry/1</code>) — one concept per governed term, carrying
          the detection seeds, governed tags, and term ids this app authors from.
        </p>
        {error && <div className="error">{error}</div>}
        {busy && <p className="loading">Loading…</p>}

        {registries.length > 0 ? (
          <>
            <h3 className="subhead">Discovered in the co-located Glossary checkout</h3>
            <div className="table-scroll">
              <table className="reg-table">
                <colgroup>
                  <col className="c-file" /><col className="c-gloss" />
                  <col className="c-concepts" /><col className="c-mod" />
                  <col style={{ width: '2.6rem' }} />
                </colgroup>
                <thead>
                  <tr><th>File</th><th>Glossary</th><th className="num">Concepts</th><th>Modified</th>
                      <th><span className="sr-only">Delete</span></th></tr>
                </thead>
                <tbody>
                  {registries.map((r) => (
                    <tr key={r.path}
                        className={r.glossary != null ? 'row-link' : undefined}
                        title={r.glossary != null ? `Load ${r.path}` : 'Unreadable or foreign file'}
                        onClick={() => r.glossary != null && loadPath(r.path)}>
                      <td className={r.glossary != null ? 'mapping-link cell-clip' : 'notes cell-clip'}>{r.file}</td>
                      <td>{r.glossary ?? <span className="notes">unreadable</span>}</td>
                      <td className="num">{r.concepts ?? '—'}</td>
                      <td className="notes">{r.modified}</td>
                      <td>
                        <button className="ghost" title={`Delete ${r.file} from disk`}
                                aria-label={`Delete ${r.file}`} disabled={busy}
                                onClick={(e) => { e.stopPropagation(); deletePath(r) }}>✕</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        ) : (
          <p className="hint-line">
            No registries auto-discovered (set <code>POLICY_REGISTRY_DIR</code> or clone
            beside the Glossary app) — upload the file instead.
          </p>
        )}
      </section>

    </>
  )
}

/* ---------- the Registry-contract explainer ---------- */

// Two-app handoff, pure inline SVG — same approach as the Glossary app's
// WorkflowDiagram (theme tokens only, no chart libraries). Static: these
// boxes are other apps, not pages of this one.
function HandoffDiagram() {
  // Laid out on a grid with three reserved bands, because the first cut let
  // arrow labels sit on their own arrows and ran the Drift loop straight
  // through the stage text ("Diagram needs tidying up"):
  //   y  28-218  the actors and the contract between them
  //   y  232     the Drift return path, in the gap below them
  //   y 246-320  what this app does with the contract
  // Verb labels are one word each; the qualifier lives under the box it
  // belongs to, where there is room for it.
  return (
    <div className="ho-wrap">
      <svg
        className="ho"
        viewBox="0 0 900 340"
        aria-label="Handoff: the Glossary Generator writes the Classification Registry at Generate.
          The Registry carries one governed row per concept — term and minted id, governed tags,
          sensitivity, category and sources, detection seeds labelled by evidence, and the
          steward's detection intent. The Policy Generator reads those rows and authors Data
          Identification methods in PDC: Author mints one method per seed, Reconcile binds each
          term by id, Deploy imports the set and Drift reads PDC back to prove deployed and
          governed still agree."
      >
        <defs>
          <marker id="ho-arrowhead" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse"
                  orient="auto-start-reverse">
            <path className="ho-head" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
          </marker>
        </defs>

        {/* band 1 — the actors, and the contract that sits between them */}
        <g className="ho-node">
          <rect x="8" y="48" width="140" height="56" rx="8" />
          <text x="78" y="72" textAnchor="middle">Glossary</text>
          <text x="78" y="90" textAnchor="middle">Generator</text>
          <text className="ho-sub" x="78" y="124" textAnchor="middle">scan, review, govern</text>
        </g>

        <path className="ho-arrow" d="M152 76 H206" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="179" y="64" textAnchor="middle">writes</text>

        <g className="ho-node ho-contract">
          <rect x="214" y="28" width="260" height="190" rx="10" />
          <text x="344" y="54" textAnchor="middle">Classification Registry</text>
          <text className="ho-sub" x="344" y="72" textAnchor="middle">written at Generate</text>
          <line className="ho-rule" x1="234" y1="86" x2="454" y2="86" />
          <text className="ho-item" x="234" y="108">term name + minted id</text>
          <text className="ho-item" x="234" y="130">governed tags (allow-list)</text>
          <text className="ho-item" x="234" y="152">sensitivity, category, sources</text>
          <text className="ho-item" x="234" y="174">detection seeds, each labelled</text>
          <text className="ho-seed" x="246" y="192">profiled · recognised · curated · name-anchored</text>
          <text className="ho-item" x="234" y="210">detection_intent (mapping-only)</text>
        </g>

        <path className="ho-arrow" d="M480 76 H534" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="507" y="64" textAnchor="middle">read by</text>

        <g className="ho-node">
          <rect x="540" y="48" width="140" height="56" rx="8" />
          <text x="610" y="72" textAnchor="middle">Policy</text>
          <text x="610" y="90" textAnchor="middle">Generator</text>
          <text className="ho-sub" x="610" y="124" textAnchor="middle">authors, never re-decides</text>
        </g>

        <path className="ho-arrow" d="M686 76 H740" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="713" y="64" textAnchor="middle">authors</text>

        <g className="ho-node">
          <rect x="746" y="48" width="146" height="56" rx="8" />
          <text x="819" y="72" textAnchor="middle">Data Identification</text>
          <text className="ho-sub" x="819" y="90" textAnchor="middle">in PDC</text>
        </g>

        {/* band 2 — Drift reads the catalog back against the contract. Routed in
            the empty gap between the sub-labels and the stage cards. */}
        <path className="ho-arrow ho-loop" d="M819 108 V232 H480" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="650" y="224" textAnchor="middle">Drift reads PDC back</text>

        {/* band 3 — the three verbs, each in its own card */}
        <g className="ho-stage">
          <rect className="ho-card" x="214" y="246" width="200" height="74" rx="8" />
          <text className="ho-stage-n" x="230" y="270">Author</text>
          <text className="ho-item" x="230" y="290">one method per seed;</text>
          <text className="ho-item" x="230" y="308">tags and term copied verbatim</text>

          <rect className="ho-card" x="430" y="246" width="200" height="74" rx="8" />
          <text className="ho-stage-n" x="446" y="270">Reconcile</text>
          <text className="ho-item" x="446" y="290">bind each term by id,</text>
          <text className="ho-item" x="446" y="308">never by name</text>

          <rect className="ho-card" x="646" y="246" width="246" height="74" rx="8" />
          <text className="ho-stage-n" x="662" y="270">Deploy → Drift</text>
          <text className="ho-item" x="662" y="290">import the set, then prove</text>
          <text className="ho-item" x="662" y="308">deployed and governed agree</text>
        </g>
      </svg>
    </div>
  )
}

// Why this app loads a file instead of scanning anything — the contract,
// told for a first-time user. Same collapsed-summary pattern as the
// Glossary app's explainer panels (details.card > summary), collapsed by
// default.
function RegistryContractExplainer() {
  return (
    <details className="card">
      <summary>Under the hood — the Registry contract</summary>
      <HandoffDiagram />
      <ul className="workcycle">
        <li>
          The <b>Glossary Generator writes the Registry at Generate</b> — the same moment
          it writes the glossary import JSONL, so both always describe the same reviewed
          state.
        </li>
        <li>
          <b>One governed row per concept</b>, carrying the facts a steward already
          decided: the business term (and its minted id once resolved), the governed tags
          from the controlled allow-list, the floor-lifted sensitivity, and the
          <b> detection seeds</b> — value regexes and reference lists induced from
          profiled data.
        </li>
        <li>
          This app <b>reads those facts instead of re-deciding them</b>: every method it
          authors copies the term, tags and seeds verbatim from the row. No hand-typed
          regex, no re-tagged column — so what PDC identifies can never quietly diverge
          from what the glossary governs.
        </li>
      </ul>
    </details>
  )
}

export function SummaryCard({ summary }) {
  const tiles = [
    { value: summary.concepts, label: 'concepts' },
    { value: summary.seeded, label: 'seeded (authorable)' },
    { value: summary.resolved_term_ids, label: 'term ids resolved' },
    { value: summary.unresolved ?? 0, label: 'unresolved ids' },
    { value: summary.governed_tags, label: 'governed tags' },
  ]
  return (
    <section className="card">
      <header>
        <h2>{summary.glossary ?? 'Registry'} <span>{summary.file}</span></h2>
        {summary.applied != null && (
          <span className="badge good">✓ {summary.applied} id(s) applied</span>
        )}
      </header>
      <div className="tiles">
        {tiles.map((t) => (
          <div className="tile" key={t.label}>
            <div className="value">{t.value}</div>
            <div className="label">{t.label}</div>
          </div>
        ))}
      </div>
      {(summary.unresolved_authorable?.length ?? 0) > 0 && (
        <p className="hint-line">
          ⚠ {summary.unresolved_authorable.length} authorable concept(s) have no term id yet —
          their methods bind by name only, which is weaker
          ({summary.unresolved_authorable.join(', ')}). Import the glossary into PDC, then
          Reconcile and Stamp ids.
        </p>
      )}
      {(summary.unresolved_authorable?.length ?? 0) === 0
        && (summary.unresolved_link_governed?.length ?? 0) > 0 && (
        <p className="hint-line">
          {summary.unresolved_link_governed.length} unresolved concept(s) are link-governed
          (mapping-only) — no method is affected ({summary.unresolved_link_governed.join(', ')}).
        </p>
      )}
    </section>
  )
}
