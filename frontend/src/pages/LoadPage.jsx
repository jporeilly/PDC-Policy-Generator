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
              <table>
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

      {summary && <SummaryCard summary={summary} />}
    </>
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
