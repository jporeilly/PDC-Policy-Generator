import { useEffect, useState } from 'react'
import PdcConnect from '../components/PdcConnect.jsx'

export default function LoadPage({ summary, onLoaded, pdc, onPdc }) {
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

      <RegistryContractExplainer />

      {summary && <SummaryCard summary={summary} />}
    </>
  )
}

/* ---------- the Registry-contract explainer ---------- */

// Two-app handoff, pure inline SVG — same approach as the Glossary app's
// WorkflowDiagram (theme tokens only, no chart libraries). Static: these
// boxes are other apps, not pages of this one.
function HandoffDiagram() {
  return (
    <div className="ho-wrap">
      <svg
        className="ho"
        viewBox="0 0 880 300"
        aria-label="Handoff: the Glossary Generator writes the Classification Registry at Generate.
          The Registry carries one governed row per concept — term and minted id, governed tags,
          and detection seeds labelled with the evidence behind them. The Policy Generator reads
          those rows and authors Data Identification methods in PDC; Reconcile binds ids against
          the live catalog, Deploy imports the set, and Drift compares what is deployed against
          what the Registry governs."
      >
        <defs>
          <marker id="ho-arrowhead" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse"
                  orient="auto-start-reverse">
            <path className="ho-head" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
          </marker>
        </defs>

        {/* --- the three actors, left to right --- */}
        <g className="ho-node">
          <rect x="8" y="40" width="150" height="58" rx="8" />
          <text x="83" y="63" textAnchor="middle">Glossary</text>
          <text x="83" y="81" textAnchor="middle">Generator</text>
          <text className="ho-sub" x="83" y="115" textAnchor="middle">scan, review, govern</text>
        </g>

        <path className="ho-arrow" d="M162 69 H206" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="184" y="59" textAnchor="middle">writes at Generate</text>

        <g className="ho-node ho-contract">
          <rect x="210" y="26" width="240" height="182" rx="10" />
          <text x="330" y="52" textAnchor="middle">Classification Registry</text>
          <text className="ho-sub" x="330" y="70" textAnchor="middle">classification-registry/1</text>
          <line className="ho-rule" x1="228" y1="82" x2="432" y2="82" />
          <text className="ho-item" x="228" y="102">term name + minted id</text>
          <text className="ho-item" x="228" y="122">governed tags (allow-list)</text>
          <text className="ho-item" x="228" y="142">sensitivity, category, sources</text>
          <text className="ho-item" x="228" y="162">detection seeds, each labelled</text>
          <text className="ho-seed" x="240" y="180">profiled · recognised · curated · name-anchored</text>
          <text className="ho-item" x="228" y="200">detection_intent (mapping-only)</text>
        </g>

        <path className="ho-arrow" d="M454 69 H498" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="476" y="59" textAnchor="middle">read by</text>

        <g className="ho-node">
          <rect x="502" y="40" width="150" height="58" rx="8" />
          <text x="577" y="63" textAnchor="middle">Policy</text>
          <text x="577" y="81" textAnchor="middle">Generator</text>
          <text className="ho-sub" x="577" y="115" textAnchor="middle">authors, never re-decides</text>
        </g>

        <path className="ho-arrow" d="M656 69 H700" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="678" y="59" textAnchor="middle">authors</text>

        <g className="ho-node">
          <rect x="704" y="40" width="168" height="58" rx="8" />
          <text x="788" y="63" textAnchor="middle">Data Identification</text>
          <text className="ho-sub" x="788" y="81" textAnchor="middle">patterns + dictionaries in PDC</text>
        </g>

        {/* --- what this app does with the contract, under the actors --- */}
        <g className="ho-stage">
          <text className="ho-stage-n" x="502" y="150">Author</text>
          <text className="ho-item" x="502" y="168">one method per seed, tags and</text>
          <text className="ho-item" x="502" y="184">term binding copied verbatim</text>

          <text className="ho-stage-n" x="502" y="212">Reconcile</text>
          <text className="ho-item" x="502" y="230">bind each term by id, not name</text>

          <text className="ho-stage-n" x="502" y="258">Deploy → Drift</text>
          <text className="ho-item" x="502" y="276">import the set, then prove deployed</text>
          <text className="ho-item" x="502" y="292">and governed still agree</text>
        </g>

        {/* Drift is the loop that closes it: PDC read back against the contract */}
        <path className="ho-arrow ho-loop" d="M788 106 V246 H470" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="640" y="240" textAnchor="middle">Drift reads PDC back</text>
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
      {(summary.unresolved ?? 0) > 0 && (
        <p className="hint-line">
          ⚠ {summary.unresolved} concept(s) have no term id yet — methods for them bind by
          name only, which is weaker. Import the glossary into PDC, then Reconcile.
        </p>
      )}
    </section>
  )
}
