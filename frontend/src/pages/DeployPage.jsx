import { useEffect, useState } from 'react'

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

export default function DeployPage({ summary, pdc, onPdc, onNavigate }) {
  const [prefix, setPrefix] = useState('')
  const [plan, setPlan] = useState(null)       // dry-run rows
  const [result, setResult] = useState(null)   // live deploy rows
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [scopeText, setScopeText] = useState('')
  const [job, setJob] = useState(null)
  const [jobStatus, setJobStatus] = useState(null)
  const [look, setLook] = useState('')          // table-name search
  const [hits, setHits] = useState(null)        // {count, entities}
  const [scopeMsg, setScopeMsg] = useState(null) // registry-scope result line
  // P3: the live deploy's phase + counter, polled while the POST runs —
  // "Working…" hid a four-phase pipeline (field: "would be good to have a
  // progress indicator when deploying")
  const [prog, setProg] = useState(null)

  // The guard returns 409 with the terms named. Offer the override where the
  // refusal appears, so the steward can act on it without reading API docs —
  // but make them choose it, and say what they are choosing.
  async function runAnyway() {
    if (!window.confirm(
      'Deploy with weak bindings?\n\n' +
      'These methods will carry the term NAME instead of PDC’s id. If anyone renames ' +
      'the term in PDC, the method silently stops being attached to it — and drift will ' +
      'not notice, because the contract and the catalog will still agree.\n\n' +
      'The fix is Reconcile → Apply → Deploy in one session.')) return
    await run(false, true)
  }

  async function run(dryRun, allowNameBinding = false) {
    if (!dryRun && !window.confirm(
      `Deploy the authored method set to PDC at ${pdc?.base}?\n` +
      'Existing methods with the same names are updated in place; the set ' +
      'stays scoped to its name prefix so Retire can always clean it up.')) return
    setBusy(true)
    setError(null)
    let poll = null
    if (!dryRun) {
      poll = setInterval(async () => {
        try {
          const r = await fetch('/api/pdc/deploy/progress')
          const d = await r.json()
          setProg(d.progress)
        } catch { /* transient — next tick retries */ }
      }, 1000)
    }
    try {
      const body = await post('/api/pdc/deploy', {
        prefix: prefix || null, dry_run: dryRun,
        ...(allowNameBinding ? { allow_name_binding: true } : {}),
      })
      if (dryRun) { setPlan(body); setResult(null) }
      else { setResult(body); setPlan(null) }
    } catch (err) {
      setError(err.message)
      if (err.message.includes('expired')) onPdc(null)
    } finally {
      if (poll) clearInterval(poll)
      setProg(null)
      setBusy(false)
    }
  }

  // Choosing a scope beats pasting one: an entity id is a uuid nobody can type
  // from memory, and a job that is tedious to scope ends up unscoped.
  async function findEntities() {
    setBusy(true); setError(null)
    try { setHits(await post('/api/pdc/entities', { q: look })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  function addToScope(id) {
    setScopeText((t) => {
      const have = t.split(/[\s,]+/).filter(Boolean)
      return have.includes(id) ? t : have.concat(id).join('\n')
    })
  }

  // You identify against what you GOVERN — and the loaded Registry already
  // knows what that is. One click resolves every governed table and file-side
  // CSV to its entity id; nobody recalls the estate from memory (which is how
  // the 2026-08-23 walk ran "nine tables" while the catalog held eleven).
  async function scopeFromRegistry() {
    setBusy(true); setError(null); setScopeMsg(null)
    try {
      const d = await post('/api/pdc/scope-candidates', {})
      const ids = d.rows.filter((r) => r.id).map((r) => r.id)
      setScopeText(ids.join('\n'))
      const named = d.rows.filter((r) => r.id)
        .map((r) => `${r.label} (${r.governed})`).join(', ')
      setScopeMsg({
        text: `scoped to the governed estate — ${d.resolved} of ${d.total} source(s): ${named}`,
        unresolved: d.unresolved,
      })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  // Firing a job and never asking how it went is how a run gets called a
  // success. The status carries the per-job lines PDC's Workers page shows.
  async function checkJob() {
    if (!job?.job_id) return
    setBusy(true); setError(null)
    try { setJobStatus(await post('/api/pdc/job', { id: job.job_id })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  // A queued job polls itself — "i have to keep clicking to see if the job
  // has finished" (field 2026-08-23). Every 5s until a terminal state or the
  // page unmounts; the manual button stays for an impatient re-check.
  useEffect(() => {
    if (!job?.job_id) return undefined
    const st = String(jobStatus?.status || '').toUpperCase()
    if (['COMPLETED', 'SUCCESS', 'FAILED', 'ERROR', 'CANCELLED'].includes(st)) return undefined
    const t = setInterval(async () => {
      try { setJobStatus(await post('/api/pdc/job', { id: job.job_id })) }
      catch { /* transient — the next tick retries */ }
    }, 5000)
    return () => clearInterval(t)
  }, [job?.job_id, jobStatus?.status])

  async function identify() {
    const scope = scopeText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean)
    if (!scope.length) { setError('paste at least one entity id to scope the job'); return }
    setBusy(true)
    setError(null)
    try {
      const j = await post('/api/pdc/identify', { prefix: result?.prefix || prefix || summary.glossary, scope })
      setJob(j)
      setJobStatus(null)
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
            {busy && prog && (
              <span className="notes">
                {prog.detail || prog.phase}
                {prog.total != null && <> · {prog.done}/{prog.total}</>}
              </span>
            )}
          </div>
        </header>
        <p className="hint-line">
          Imports the authored set programmatically over the same path PDC 11's UI
          zip-upload uses, waits for the import workers, verifies every method landed,
          then re-stamps the Registry's minted term ids into each method's term binding
          (the importer rewrites ids it cannot resolve). Dry-run shows the create/update
          plan without touching PDC.
        </p>
        {/* P2/P4: the banner names its concepts and only goes amber when a
            METHOD is affected — a mapping-only concept with no term id authors
            nothing, so name-binding cannot happen and the remedy is moot. */}
        {(summary.unresolved_authorable?.length ?? 0) > 0 && (
          <p className="summary">
            <span className="badge warning" title="Run Reconcile and click Stamp ids first — the reconcile rows showing a found id are not applied until stamped">
              ⚠ {summary.unresolved_authorable.length} authorable concept(s) have no term id — their
              methods bind by name: {summary.unresolved_authorable.join(', ')}. Reconcile, then Stamp ids.
            </span>
          </p>
        )}
        {(summary.unresolved_authorable?.length ?? 0) === 0
          && (summary.unresolved_link_governed?.length ?? 0) > 0 && (
          <p className="notes">
            {summary.unresolved_link_governed.length} unresolved concept(s) are link-governed
            (mapping-only) — no method is affected: {summary.unresolved_link_governed.join(', ')}.
          </p>
        )}
        {error && (
          <div className="error">
            {error}
            {error.includes('bind by NAME') && (
              <div className="actions" style={{ marginTop: '.6rem' }}>
                <button className="ghost" onClick={() => onNavigate?.('reconcile')}>
                  → Reconcile first (recommended)
                </button>
                <button className="ghost" onClick={runAnyway} disabled={busy}>
                  Deploy anyway, with weak bindings
                </button>
              </div>
            )}
          </div>
        )}

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
        {/* WHICH one broke it. PDC's importer abandons the rest of the zip at
            the first member it cannot read, reports COMPLETED anyway, and its
            error never names the file — so the deploy table showed a wall of
            "not found" with no cause. The first absent method of that kind IS
            where it stopped. */}
        {/* P5: a worker that never reached a terminal state read NOTHING — a
            different failure from a parse-abandoned archive, and the walk's
            VM proved the misdiagnosis costs real hunting time. */}
        {result?.workers?.filter((w) => w.never_ran).map((w) => (
          <div className="error" key={`nr-${w.kind}`}>
            <b>{w.kind} import never started.</b> {w.why}
          </div>
        ))}
        {result?.workers?.filter((w) => w.stopped_at).map((w) => (
          <div className="error" key={`stop-${w.kind}`}>
            <b>{w.kind} import stopped at “{w.stopped_at}”.</b>{' '}
            {w.lost_after > 0 && (
              <>The {w.lost_after} method(s) queued after it in the zip were never
              read — PDC abandons the rest of the archive at the first member it
              cannot parse, and still reports {w.status}. </>
            )}
            {w.exception
              ? <>PDC said: <code>{w.exception}</code></>
              : <>PDC reported no error, so check that method’s values and rule.</>}
          </div>
        ))}
        {plan && (
          <>
            <p className="summary">
              <span className="badge accent" style={{ marginRight: '1rem' }}>+ create {plan.counts.create}</span>
              <span className="badge neutral">↻ update {plan.counts.update}</span>
            </p>
            {/* the dry run reports what a real deploy would refuse over, so the
                problem is found here rather than in a 409 */}
            {plan.name_binding?.blocks_deploy && (
              <p className="summary">
                <span className="badge warning">
                  ⚠ {plan.name_binding.count} method(s) would bind by name — deploy will refuse
                </span>
                <span className="notes" style={{ display: 'block', marginTop: '.35rem' }}>
                  {plan.name_binding.terms.join(', ')}
                  {plan.name_binding.count > plan.name_binding.terms.length ? ' …' : ''}
                  {' — '}Reconcile, Apply, then deploy in the same session.
                </span>
              </p>
            )}
          </>
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
                        r.never_ran
                          ? <span className="badge neutral" title="The import worker never processed the archive — nothing was read; redeploy once the worker queue is healthy.">◌ import never ran</span>
                          : <span className="badge serious" title={r.error ?? ''}>✋ not found after import</span>
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
            <button className="primary" onClick={identify} disabled={busy || !pdc || !result}>
              ▶ Start DATA_IDENTIFICATION job
            </button>
          </div>
        </header>
        <p className="hint-line">
          Trigger one DATA_IDENTIFICATION bulk job scoped to the deployed method set and
          to the entity ids below (from PDC's catalog — a data source or folder id per
          line). Never catalog-wide from here; deploy first.
        </p>
        <div className="actions">
          <button className="primary" onClick={scopeFromRegistry} disabled={busy || !pdc}>
            ⛭ Scope from Registry
          </button>
          <input className="text" value={look} onChange={(e) => setLook(e.target.value)}
                 placeholder="find a table by name, e.g. customers"
                 onKeyDown={(e) => { if (e.key === 'Enter') findEntities() }} />
          <button className="ghost" onClick={findEntities} disabled={busy || !pdc || look.trim().length < 2}>
            🔍 Find tables
          </button>
        </div>
        {scopeMsg && (
          <p className={`summary ${scopeMsg.unresolved?.length ? 'warn' : 'ok'}`}>
            {scopeMsg.text}
            {scopeMsg.unresolved?.length > 0 &&
              <> · not found in PDC (register/bulk-load them first): {scopeMsg.unresolved.join(', ')}</>}
          </p>
        )}
        {hits && (
          hits.count === 0
            ? <p className="hint-line">Nothing in the catalog matches “{hits.q}”.</p>
            : <div className="table-scroll" style={{ maxHeight: '220px', overflowY: 'auto' }}>
                <table>
                  <thead><tr><th>Entity</th><th>Type</th><th>Path</th><th /></tr></thead>
                  <tbody>
                    {hits.entities.map((e) => (
                      <tr key={e.id}>
                        <td>{e.name}</td>
                        <td className="notes">{e.type}</td>
                        <td className="notes cell-clip" title={e.path}>{e.path}</td>
                        <td>
                          <button className="ghost" onClick={() => addToScope(e.id)}
                                  title={`Add ${e.id} to the scope`}>+ scope</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
        )}
        <div className="form-grid">
          <label>Entity ids (one per line)
            <textarea className="text" rows={3} value={scopeText}
                      onChange={(e) => setScopeText(e.target.value)}
                      placeholder="pick tables above, or paste entity ids" />
          </label>
        </div>
        {job && (
          <>
            <p className="summary">
              <span className="badge good" title={`methods in scope: ${job.methods}`}>
                ✓ job queued — id {job.job_id ?? '—'} · {job.methods} method(s) · {job.scope} entity id(s)
              </span>
              <button className="ghost" style={{ marginLeft: '.6rem' }}
                      onClick={checkJob} disabled={busy || !job.job_id}>
                {busy ? 'Checking…' : '↻ Check now'}
              </button>
              {!['COMPLETED', 'SUCCESS', 'FAILED', 'ERROR', 'CANCELLED']
                .includes(String(jobStatus?.status || '').toUpperCase()) && (
                <span className="notes" style={{ marginLeft: '.6rem' }}>
                  auto-refreshing every 5s until the worker finishes
                </span>
              )}
            </p>
            {jobStatus && (
              jobStatus.found === false
                ? <p className="hint-line">
                    PDC has no worker carrying that id{jobStatus.error ? ` — ${jobStatus.error}` : ''}.
                  </p>
                : <>
                    <p className="summary">
                      <span className={`badge ${jobStatus.status === 'COMPLETED' ? 'good'
                        : jobStatus.status === 'FAILED' ? 'serious' : 'accent'}`}>
                        {jobStatus.label ?? 'job'} — {jobStatus.status ?? 'unknown'}
                      </span>
                    </p>
                    {/* the per-job lines are the part that says whether the scope
                        was actually covered — a COMPLETED worker can still have
                        processed a fraction of what it was given */}
                    {(jobStatus.jobs ?? []).length > 0 && (
                      <div className="table-scroll">
                        <table>
                          <thead><tr><th>Job</th><th>Status</th><th>Processed</th></tr></thead>
                          <tbody>
                            {jobStatus.jobs.map((j, i) => {
                              const st = j.statistics ?? {}
                              const done = st.COMPLETED ?? 0
                              const total = st.TOTAL ?? 0
                              return (
                                <tr key={i}>
                                  <td>{j.label ?? '—'}</td>
                                  <td>
                                    <span className={`badge ${j.status === 'COMPLETED' ? 'good' : 'accent'}`}>
                                      {j.status ?? '—'}
                                    </span>
                                  </td>
                                  <td className={total && done < total ? 'notes warning' : 'notes'}>
                                    {total ? `${done} of ${total}` : '—'}
                                    {st.FAILED ? ` · ${st.FAILED} failed` : ''}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
            )}
          </>
        )}
      </section>
    </>
  )
}
