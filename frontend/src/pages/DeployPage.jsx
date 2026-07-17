import { useState } from 'react'

/* Deploy — import the authored method set into PDC over the discovered
   import API (multipart /api/importWorkerFiles — the same path PDC 11's own
   UI zip-upload takes), then re-stamp the Registry's term ids. Table and
   result chrome mirror the Reconcile page. */

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

// What one Deploy actually runs, step by step — the suite's expandable
// explainer pattern (details.card > summary, collapsed by default).
function WhatDeployDoesExplainer() {
  return (
    <details className="card">
      <summary>Under the hood — what Deploy does</summary>
      <ul className="workcycle">
        <li>
          <b>Imports over PDC's own worker API.</b> The exact zips Author produces are
          uploaded as multipart <code>POST /api/importWorkerFiles</code> — the same path
          PDC 11's UI zip-upload takes — then the import workers are polled to completion.
        </li>
        <li>
          <b>Deterministic ids make re-deploy an upsert.</b> Every method carries a
          deterministic <code>_id</code>, so deploying again updates the same method in
          place — never a duplicate.
        </li>
        <li>
          <b>Term ids are re-stamped after import.</b> PDC's importer rewrites a term id
          it cannot resolve, so Deploy verifies every method landed and writes the
          Registry's minted ids back into each term binding.
        </li>
        <li>
          <b>Everything stays under the name prefix</b> — the scoped Retire on the
          Reconcile page can always clean up exactly this set, nothing else.
        </li>
        <li>
          <b>Dry-run is free.</b> Preview returns the create/update plan without touching
          PDC.
        </li>
      </ul>
    </details>
  )
}

export default function DeployPage({ summary, pdc, onPdc }) {
  const [prefix, setPrefix] = useState('')
  const [plan, setPlan] = useState(null)       // dry-run rows
  const [result, setResult] = useState(null)   // live deploy rows
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [scopeText, setScopeText] = useState('')
  const [job, setJob] = useState(null)

  async function run(dryRun) {
    if (!dryRun && !window.confirm(
      `Deploy the authored method set to PDC at ${pdc?.base}?\n` +
      'Existing methods with the same names are updated in place; the set ' +
      'stays scoped to its name prefix so Retire can always clean it up.')) return
    setBusy(true)
    setError(null)
    try {
      const body = await post('/api/pdc/deploy', { prefix: prefix || null, dry_run: dryRun })
      if (dryRun) { setPlan(body); setResult(null) }
      else { setResult(body); setPlan(null) }
    } catch (err) {
      setError(err.message)
      if (err.message.includes('expired')) onPdc(null)
    } finally {
      setBusy(false)
    }
  }

  async function identify() {
    const scope = scopeText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)
    if (!scope.length) { setError('paste at least one entity id to scope the job'); return }
    setBusy(true)
    setError(null)
    try {
      setJob(await post('/api/pdc/identify', { prefix: result?.prefix || prefix || summary.glossary, scope }))
    } catch (err) {
      setError(err.message)
      if (err.message.includes('expired')) onPdc(null)
    } finally {
      setBusy(false)
    }
  }

  const rows = result?.rows ?? plan?.rows ?? []
  const isPlan = !!plan

  return (
    <>
      <section className="card">
        <header>
          <h2>
            Deploy to PDC
            {pdc && (
              <span className="badge good" title={`roles: ${(pdc.roles ?? []).join(', ')}`}>
                ✓ {pdc.username ?? 'connected'} @ {pdc.base}
              </span>
            )}
          </h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <input className="text" placeholder="Name prefix (default: glossary name)"
                   value={prefix} onChange={(e) => setPrefix(e.target.value)} />
            <button className="ghost" onClick={() => run(true)} disabled={busy || !pdc}>
              {busy ? 'Working…' : 'Preview (dry-run)'}
            </button>
            <button className="primary" onClick={() => run(false)} disabled={busy || !pdc}>
              🚀 Deploy
            </button>
          </div>
        </header>
        <p className="hint-line">
          Imports the authored set programmatically over the same path PDC 11's UI
          zip-upload uses, waits for the import workers, verifies every method landed,
          then re-stamps the Registry's minted term ids into each method's term binding
          (the importer rewrites ids it cannot resolve). Dry-run shows the create/update
          plan without touching PDC.
        </p>
        {summary.unresolved > 0 && (
          <p className="summary">
            <span className="badge warning" title="Run Reconcile and apply the found ids first — deploy binds terms by id">
              ⚠ {summary.unresolved} concept(s) still have no term id — those methods bind by name only
            </span>
          </p>
        )}
        {error && <div className="error">{error}</div>}

        {result?.workers?.length > 0 && (
          <p className="summary">
            {result.workers.map((w) => (
              <span key={w.kind} style={{ marginRight: '1rem' }}>
                <span className={`badge ${w.status === 'COMPLETED' ? 'good' : w.status === 'FAILED' ? 'serious' : 'warning'}`}
                      title={`${w.workerName} · worker ${w.worker_id}`}>
                  {w.kind} import: {w.status ?? 'running'}
                </span>
              </span>
            ))}
          </p>
        )}
        {result && (
          <p className="summary">
            <span className="badge good" style={{ marginRight: '1rem' }}>✓ imported {result.counts.imported}</span>
            <span className="badge accent" style={{ marginRight: '1rem' }}>⚭ id-bound {result.counts.bound}</span>
            {result.counts.failed > 0 && <span className="badge serious">✋ failed {result.counts.failed}</span>}
          </p>
        )}
        {plan && (
          <p className="summary">
            <span className="badge accent" style={{ marginRight: '1rem' }}>+ create {plan.counts.create}</span>
            <span className="badge neutral">↻ update {plan.counts.update}</span>
          </p>
        )}

        {rows.length > 0 && (
          <div className="table-scroll" style={{ maxHeight: '420px', overflowY: 'auto' }}>
            <table>
              <thead>
                <tr><th>Method</th><th>Kind</th><th>Term</th><th>Bound</th>
                    <th>{isPlan ? 'Plan' : 'Result'}</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.kind}:${r.name}`}>
                    <td>{r.name}</td>
                    <td className="notes">{r.kind}</td>
                    <td>{r.term}</td>
                    <td>{r.term_id
                      ? <span className="badge good" title={r.term_id}>✓ by id</span>
                      : <span className="badge warning" title="No term id in the Registry — binds by name">⚠ by name</span>}</td>
                    <td>
                      {isPlan && (r.action === 'create'
                        ? <span className="badge accent">+ create</span>
                        : <span className="badge neutral">↻ update</span>)}
                      {!isPlan && r.imported && (
                        <span className="badge good" title={r._id ?? ''}>
                          ✓ imported{r.bound === true ? ' + bound' : r.bound === false ? ' (bind failed)' : ''}
                        </span>
                      )}
                      {!isPlan && !r.imported && (
                        <span className="badge serious" title={r.error ?? ''}>✋ not found after import</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <WhatDeployDoesExplainer />

      <section className="card">
        <header>
          <h2>Run identification <span>optional</span></h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <button className="ghost" onClick={identify} disabled={busy || !pdc || !result}>
              ▶ Start DATA_IDENTIFICATION job
            </button>
          </div>
        </header>
        <p className="hint-line">
          Trigger one DATA_IDENTIFICATION bulk job scoped to the deployed method set and
          to the entity ids below (from PDC's catalog — a data source or folder id per
          line). Never catalog-wide from here; deploy first.
        </p>
        <div className="form-grid">
          <label>Entity ids (one per line)
            <textarea className="text" rows={3} value={scopeText}
                      onChange={(e) => setScopeText(e.target.value)}
                      placeholder="e.g. 64f1c0…  (Data Sources → id)" />
          </label>
        </div>
        {job && (
          <p className="summary">
            <span className="badge good" title={`methods in scope: ${job.methods}`}>
              ✓ job queued — id {job.job_id ?? '—'} · {job.methods} method(s) · {job.scope} entity id(s)
            </span>
          </p>
        )}
      </section>
    </>
  )
}
