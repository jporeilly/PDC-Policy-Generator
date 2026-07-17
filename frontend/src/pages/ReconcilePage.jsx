import { useState } from 'react'

const STATUS = {
  verified: { cls: 'good', icon: '✓', tip: 'PDC id matches the Registry id' },
  resolved: { cls: 'accent', icon: 'ℹ', tip: 'Found in PDC; Registry had no id — apply to bind' },
  mismatch: { cls: 'warning', icon: '⚠', tip: 'PDC id differs from the Registry id — apply to rebind' },
  missing: { cls: 'serious', icon: '✋', tip: 'Term not found in PDC — import the glossary first' },
}

const BATCH = 25

export default function ReconcilePage({ summary, onSummary, pdc, onPdc }) {
  // pdc (the connected-session info) lives in App state: Deploy and Drift gate on it
  const [form, setForm] = useState({ base_url: '', username: '', password: '', token: '', verify_tls: false })
  const [rows, setRows] = useState([])
  const [counts, setCounts] = useState(null)
  const [progress, setProgress] = useState(null) // {done, total}
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [methods, setMethods] = useState(null)
  const [prefix, setPrefix] = useState('')

  async function post(url, body) {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || res.statusText)
    return data
  }

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      onPdc(await post('/api/pdc/connect', form))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function reconcile() {
    setBusy(true)
    setError(null)
    setRows([])
    setCounts(null)
    try {
      let offset = 0
      let all = []
      for (;;) {
        const b = await post('/api/reconcile', { offset, limit: BATCH })
        all = [...all, ...b.rows]
        setRows(all)
        setProgress({ done: b.done, total: b.total })
        if (b.finished) {
          setCounts(b.counts)
          break
        }
        offset = b.done
      }
    } catch (err) {
      setError(err.message)
      if (err.message.includes('expired')) onPdc(null)
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  async function applyIds() {
    setBusy(true)
    setError(null)
    try {
      onSummary(await post('/api/reconcile/apply'))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function listMethods() {
    setBusy(true)
    setError(null)
    try {
      setMethods(await post('/api/pdc/methods', { prefix: prefix || null }))
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  async function retire() {
    if (!prefix.trim()) {
      setError('retire is always scoped — enter the name prefix first')
      return
    }
    const count = methods?.methods?.filter((m) => !m.builtIn).length ?? '?'
    if (!window.confirm(
      `Retire (DELETE) ${count} method(s) named "${prefix}…" from PDC?\n` +
      'Built-ins are never touched. This cannot be undone.')) return
    setBusy(true)
    setError(null)
    try {
      const res = await post('/api/pdc/retire', { prefix })
      setMethods({ methods: res.results, count: res.results.length, prefix })
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
          <h2>Connect to PDC</h2>
          {pdc && (
            <span className="badge good" title={`roles: ${(pdc.roles ?? []).join(', ')}`}>
              ✓ {pdc.username ?? 'connected'} @ {pdc.base}
            </span>
          )}
        </header>
        <p className="hint-line">
          The token lives in memory for this session only; the password is never stored.
        </p>
        <div className="form-grid">
          <label>Base URL
            <input placeholder="https://192.168.1.200" value={form.base_url}
                   onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
          </label>
          <label>Username
            <input value={form.username}
                   onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </label>
          <label>Password
            <input type="password" value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </label>
          <label>Bearer token (instead of credentials)
            <input value={form.token}
                   onChange={(e) => setForm({ ...form, token: e.target.value })} />
          </label>
        </div>
        <div className="actions">
          <label className="check">
            <input type="checkbox" checked={form.verify_tls}
                   onChange={(e) => setForm({ ...form, verify_tls: e.target.checked })} />
            Verify TLS certificate
          </label>
          <button className="primary" onClick={connect} disabled={busy}>
            {busy ? 'Connecting…' : pdc ? '↻ Reconnect' : 'Connect'}
          </button>
        </div>
        {error && <div className="error">{error}</div>}
      </section>

      <section className="card">
        <header>
          <h2>Reconcile term ids <span>{summary.concepts} concepts</span></h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <button className="primary" onClick={reconcile} disabled={busy || !pdc}>
              {busy && progress ? `Reconciling ${progress.done}/${progress.total}…` : '⇄ Run reconcile'}
            </button>
            {counts && (counts.resolved + counts.mismatch) > 0 && (
              <button className="ghost" onClick={applyIds} disabled={busy}>
                Apply {counts.resolved + counts.mismatch} id(s) to Registry
              </button>
            )}
            {summary.applied != null && (
              <a className="badge accent" href="/api/registry/export">⬇ Export reconciled registry</a>
            )}
          </div>
        </header>
        {progress && (
          <div className="progress-track">
            <div className="progress-bar" style={{ width: `${(progress.done / progress.total) * 100}%` }} />
          </div>
        )}
        {counts && (
          <p className="summary">
            {Object.entries(STATUS).map(([k, s]) =>
              <span key={k} title={s.tip} style={{ marginRight: '1rem' }}>
                <span className={`badge ${s.cls}`}>{s.icon} {k} {counts[k]}</span>
              </span>)}
          </p>
        )}
        {rows.length > 0 && (
          <div className="table-scroll" style={{ maxHeight: '420px', overflowY: 'auto' }}>
            <table>
              <thead>
                <tr><th>Term</th><th>Status</th><th>Registry id</th><th>PDC id</th><th>Seeded</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const s = STATUS[r.status]
                  return (
                    <tr key={r.term}>
                      <td>{r.term}</td>
                      <td><span className={`badge ${s.cls}`} title={s.tip}>{s.icon} {r.status}</span></td>
                      <td className="mono cell-clip" title={r.registry_id ?? ''}>{r.registry_id ?? '—'}</td>
                      <td className="mono cell-clip" title={r.pdc_id ?? ''}>{r.pdc_id ?? '—'}</td>
                      <td className="notes">{r.seeded ? 'yes' : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <header>
          <h2>Imported method set</h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <input className="text" placeholder="Name prefix (the authored set)"
                   value={prefix} onChange={(e) => setPrefix(e.target.value)} />
            <button className="ghost" onClick={listMethods} disabled={busy || !pdc}>List methods</button>
            <button className="ghost" onClick={retire} disabled={busy || !pdc || !methods?.count}
                    title="Delete the prefixed set from PDC (built-ins never touched)">
              🗑 Retire set…
            </button>
          </div>
        </header>
        <p className="hint-line">
          Read-only preview of the custom Data Identification methods in PDC, scoped to
          your prefix. Retire deletes exactly that scoped set — PDC's own UI has no Delete.
        </p>
        {methods && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Name</th><th>Kind</th><th>Enabled</th><th>Result</th></tr>
              </thead>
              <tbody>
                {methods.methods.map((m) => (
                  <tr key={m._id}>
                    <td>{m.name}</td>
                    <td className="notes">{m.kind}</td>
                    <td className="notes">{m.isEnabled === false ? 'no' : 'yes'}</td>
                    <td>
                      {m.removed === true && <span className="badge good">✓ removed</span>}
                      {m.removed === false && <span className="badge serious" title={m.error}>✋ failed</span>}
                      {m.removed === undefined && <span className="notes">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  )
}
