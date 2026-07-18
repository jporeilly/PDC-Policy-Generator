import { useEffect, useState } from 'react'

export default function LoadPage({ summary, onLoaded }) {
  const [registries, setRegistries] = useState([])
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetch('/api/registries')
      .then((r) => r.json())
      .then((b) => setRegistries(b.registries ?? []))
      .catch(() => {})
  }, [])

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
                </colgroup>
                <thead>
                  <tr><th>File</th><th>Glossary</th><th className="num">Concepts</th><th>Modified</th></tr>
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
        viewBox="0 0 560 92"
        aria-label="Handoff: the Glossary Generator writes the Classification Registry at Generate;
          the Policy Generator reads it and authors Data Identification methods in PDC."
      >
        <defs>
          <marker id="ho-arrowhead" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse"
                  orient="auto-start-reverse">
            <path className="ho-head" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
          </marker>
        </defs>

        <path className="ho-arrow" d="M116 46 H138" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="127" y="36" textAnchor="middle">writes</text>
        <path className="ho-arrow" d="M278 46 H300" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="289" y="36" textAnchor="middle">read by</text>
        <path className="ho-arrow" d="M412 46 H434" markerEnd="url(#ho-arrowhead)" />
        <text className="ho-label" x="423" y="36" textAnchor="middle">authors</text>

        <g className="ho-node">
          <rect x="2" y="26" width="114" height="40" rx="8" />
          <text x="59" y="43" textAnchor="middle" dominantBaseline="middle">Glossary</text>
          <text x="59" y="57" textAnchor="middle" dominantBaseline="middle">Generator</text>
        </g>
        <g className="ho-node ho-contract">
          <rect x="140" y="26" width="138" height="40" rx="8" />
          <text x="209" y="43" textAnchor="middle" dominantBaseline="middle">Classification</text>
          <text x="209" y="57" textAnchor="middle" dominantBaseline="middle">Registry</text>
          <text className="ho-sub" x="209" y="80" textAnchor="middle">the contract — one governed row per concept</text>
        </g>
        <g className="ho-node">
          <rect x="302" y="26" width="110" height="40" rx="8" />
          <text x="357" y="43" textAnchor="middle" dominantBaseline="middle">Policy</text>
          <text x="357" y="57" textAnchor="middle" dominantBaseline="middle">Generator</text>
        </g>
        <g className="ho-node">
          <rect x="436" y="26" width="122" height="40" rx="8" />
          <text x="497" y="43" textAnchor="middle" dominantBaseline="middle">Data Identification</text>
          <text className="ho-sub" x="497" y="57" textAnchor="middle" dominantBaseline="middle">in PDC</text>
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
      {(summary.unresolved ?? 0) > 0 && (
        <p className="hint-line">
          ⚠ {summary.unresolved} concept(s) have no term id yet — methods for them bind by
          name only, which is weaker. Import the glossary into PDC, then Reconcile.
        </p>
      )}
    </section>
  )
}
