import { useState } from 'react'

const STATUS = {
  verified: { cls: 'good', icon: '✓', tip: 'PDC id matches the Registry id' },
  resolved: { cls: 'accent', icon: 'ℹ', tip: 'Found in PDC; Registry had no id — apply to bind' },
  mismatch: { cls: 'warning', icon: '⚠', tip: 'PDC id differs from the Registry id — apply to rebind' },
  missing: { cls: 'serious', icon: '✋', tip: 'Term not found in PDC — import the glossary first' },
}

const BATCH = 25

export default function ReconcilePage({ summary, onSummary, pdc, onNavigate }) {
  // pdc (the connected-session info) lives in App state: Deploy and Drift gate on it
  const [rows, setRows] = useState([])
  const [counts, setCounts] = useState(null)
  const [progress, setProgress] = useState(null) // {done, total}
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [methods, setMethods] = useState(null)
  const [builtins, setBuiltins] = useState(null)     // {built_in, by_kind, changed…}
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

  async function builtinsPlan() {
    setBusy(true); setError(null)
    try { setBuiltins(await post('/api/pdc/builtins', { dry_run: true })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  async function builtinsSet(enabled) {
    // Count first if nobody has. These buttons used to sit DISABLED until
    // "Count them" had run, with nothing on screen saying so — a control that
    // does nothing and reports nothing (field-caught: "I've clicked Disable
    // built-ins several times, seems as though it's disabled (joke)"). The
    // count is one call and the action needs the number for its own prompt,
    // so it fetches its own.
    let plan = builtins
    if (!plan?.built_in) {
      setBusy(true); setError(null)
      try {
        plan = await post('/api/pdc/builtins', { dry_run: true })
        setBuiltins(plan)
      } catch (err) {
        setError(err.message); setBusy(false); return
      }
      setBusy(false)
    }
    if (!plan?.built_in) {
      setError('PDC reports no built-in methods to change.')
      return
    }
    const n = plan.built_in
    if (!window.confirm(
      `${enabled ? 'Enable' : 'Disable'} ${n} BUILT-IN method(s) in PDC?

` +
      'This is catalog-wide, not scoped to your prefix — it affects every glossary and ' +
      'every future scan in this PDC. Your own authored methods are never touched, and ' +
      'the same action with the opposite setting puts these back.')) return
    setBusy(true); setError(null)
    try { setBuiltins(await post('/api/pdc/builtins', { enabled, dry_run: false })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
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
      {pdc ? (
        <p className="hint-line">
          Working against <b>{pdc.username ?? 'PDC'}</b> @ <b>{pdc.base}</b>
          {pdc.expires_in != null && <> · token good for {Math.round(pdc.expires_in / 60)} min</>}
          {' — '}connect or switch session on the <button className="link-inline"
            onClick={() => onNavigate?.('load')}>Load page</button>.
        </p>
      ) : (
        <section className="card">
          <p className="hint-line">
            ⚠ No PDC session. Reconcile reads live term ids, so it needs one —
            <button className="link-inline" onClick={() => onNavigate?.('load')}>
              connect on the Load page
            </button>, then come back.
          </p>
        </section>
      )}

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
          <div className="recon-progress">
            <div className="progress-track">
              <div className={`progress-bar${busy ? '' : ' done'}`}
                   style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }} />
            </div>
            <p className="notes" aria-live="polite">
              {busy
                ? <>Reconciling <b>{progress.done}</b> of <b>{progress.total}</b> concept(s)
                    {' '}({Math.round((progress.done / progress.total) * 100)}%) — looking each term
                    up in PDC in batches of {BATCH}.</>
                : <>Reconciled <b>{progress.done}</b> of <b>{progress.total}</b> concept(s).</>}
              {rows.length > 0 && (
                <> Verified {rows.filter((r) => r.status === 'verified').length},
                  {' '}resolved {rows.filter((r) => r.status === 'resolved').length},
                  {' '}mismatch {rows.filter((r) => r.status === 'mismatch').length},
                  {' '}missing {rows.filter((r) => r.status === 'missing').length} so far.</>
              )}
            </p>
          </div>
        )}
        {counts && (
          <div className="chips-row">
            {Object.entries(STATUS).map(([k, s]) =>
              <span key={k} className={`badge ${s.cls}`} title={s.tip}>{s.icon} {k} {counts[k]}</span>)}
          </div>
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
          <h2>Built-in methods <span>PDC ships these enabled</span></h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <button className="ghost" onClick={builtinsPlan} disabled={busy || !pdc}>
              {busy ? 'Reading…' : '↻ Count them'}
            </button>
            <button className="primary" onClick={() => builtinsSet(false)}
                    disabled={busy || !pdc}
                    title="Disable every built-in pattern and dictionary (reversible)">
              ⦸ Disable built-ins…
            </button>
            <button className="ghost" onClick={() => builtinsSet(true)}
                    disabled={busy || !pdc}
                    title="Put every built-in back">
              ↺ Restore…
            </button>
          </div>
        </header>
        <p className="hint-line">
          An identification job started anywhere other than this app — PDC's own screen, a
          schedule, ingest — classifies against whatever is <b>enabled</b>. In a custom-only
          programme that means shapes induced from somebody else's data competing with shapes
          induced from your estate: the drift the programme exists to prevent. Disabling them is
          catalog-wide and reversible, and never touches a method this app authored.
        </p>
        {builtins && (
          <>
            <div className="chips-row">
              <span className="badge neutral">{builtins.built_in} built-in</span>
              <span className="badge neutral">
                {builtins.by_kind?.DataPattern ?? 0} patterns · {builtins.by_kind?.Dictionary ?? 0} dictionaries
              </span>
              <span className="badge good">{builtins.custom_untouched} custom untouched</span>
              {builtins.dry_run
                ? <span className="badge accent">plan only — nothing written</span>
                : <span className={`badge ${builtins.failed ? 'warning' : 'good'}`}>
                    {builtins.changed} {builtins.enabled ? 'enabled' : 'disabled'}
                    {builtins.failed ? ` · ${builtins.failed} failed` : ''}
                  </span>}
              {/* the count the ESTATE agrees with, read back after the write */}
              {!builtins.dry_run && builtins.verified != null && (
                <span className={`badge ${builtins.unverified ? 'warning' : 'good'}`}>
                  {builtins.unverified
                    ? `${builtins.unverified} NOT ${builtins.enabled ? 'enabled' : 'disabled'} in PDC`
                    : `confirmed ${builtins.enabled ? 'enabled' : 'disabled'} in PDC — read back`}
                </span>
              )}
            </div>
            {!builtins.dry_run && builtins.unverified > 0 && (
              <>
                <p className="hint-line">
                  PDC accepted the call and these are still{' '}
                  <b>{builtins.enabled ? 'disabled' : 'enabled'}</b>. An identification job
                  will classify against them — re-run, or turn them off in PDC directly.
                </p>
                <div className="table-scroll" style={{ maxHeight: '220px', overflowY: 'auto' }}>
                  <table>
                    <thead><tr><th>Method</th><th>State in PDC</th></tr></thead>
                    <tbody>
                      {builtins.unverified_rows.map((r) => (
                        <tr key={`${r.kind}-${r.name}`}>
                          <td>{r.name}</td>
                          <td className="notes">{r.error || (r.isEnabled ? 'enabled' : 'disabled')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
            {!builtins.dry_run && builtins.failed > 0 && (
              <div className="table-scroll" style={{ maxHeight: '220px', overflowY: 'auto' }}>
                <table>
                  <thead><tr><th>Method</th><th>Error</th></tr></thead>
                  <tbody>
                    {builtins.rows.filter((r) => !r.ok).map((r) => (
                      <tr key={r.name}><td>{r.name}</td><td className="notes">{r.error}</td></tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
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
