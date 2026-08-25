import { useCallback, useEffect, useState } from 'react'

/**
 * The Report page: one account of the whole pipeline, from the contract to what
 * is actually deployed.
 *
 * It exists because the interesting facts were spread across four pages and a
 * terminal. "115 methods authored" means little on its own; "115 authored, 67 of
 * them resting on a column name, 115 live in PDC, 0 drifted" is a governance
 * statement someone can act on. Everything here is read back from the Registry,
 * the authored set, and (when a session exists) the live catalog — nothing is
 * remembered from earlier in the session, so the page cannot flatter itself.
 */
const EVIDENCE_NOTE = {
  profiled: 'induced from the estate’s own values by the Glossary scan',
  recognised: 'the profiler matched a known kind (email, phone, …) in this estate’s data',
  curated: 'a vetted seed from the versioned domain pack',
  'name-anchored': 'the steward declared the column NAME authoritative; the content regex is a sanity check only',
}

function pct(n, of) {
  return of ? `${Math.round((n / of) * 100)}%` : '—'
}

export default function ReportPage({ summary, pdc, prefix: initialPrefix }) {
  const [preview, setPreview] = useState(null)
  const [drift, setDrift] = useState(null)
  const [live, setLive] = useState(null)
  const [prefix, setPrefix] = useState(initialPrefix || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [stampedAt, setStampedAt] = useState(null)
  const [tables, setTables] = useState('')        // names to read identification back from
  const [ident, setIdent] = useState(null)

  // Prefill the read-back scope from the Registry: you read back what you
  // GOVERN, and nobody should have to recall the estate's table names (the
  // scope box and this field asked twice; the Registry knew both times).
  // Files are excluded — the read-back walks TABLE/VIEW children only.
  useEffect(() => {
    if (tables) return undefined
    let dead = false
    fetch('/api/scope-sources').then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (!dead && d?.tables?.length) setTables(d.tables.map((t) => t.name).join(' '))
    }).catch(() => {})
    return () => { dead = true }
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const post = async (url, body) => {
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || res.statusText)
    return data
  }

  const compile = useCallback(async () => {
    setBusy(true)
    setError(null)
    try {
      const pv = await post('/api/preview', prefix ? { prefix } : {})
      setPreview(pv)
      setPrefix((p) => p || pv.prefix || '')
      if (pdc) {
        const p = prefix || pv.prefix
        const [d, m] = await Promise.all([
          post('/api/pdc/drift', { prefix: p }).catch(() => null),
          post('/api/pdc/methods', { prefix: p }).catch(() => null),
        ])
        setDrift(d)
        setLive(m)
      } else {
        setDrift(null)
        setLive(null)
      }
      setStampedAt(new Date().toLocaleTimeString())
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [prefix, pdc])

  useEffect(() => { compile() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  const patterns = preview?.patterns ?? []
  const dicts = preview?.dictionaries ?? []
  const authored = patterns.length + dicts.length
  const evidence = [...patterns, ...dicts].reduce((acc, m) => {
    acc[m.evidence] = (acc[m.evidence] ?? 0) + 1
    return acc
  }, {})
  const boundById = [...patterns, ...dicts].filter((m) => m.term_id).length
  const skipGroups = (preview?.skipped ?? []).reduce((acc, s) => {
    const k = s.why ?? 'unstated'
    acc[k] = (acc[k] ?? 0) + 1
    return acc
  }, {})

  // Deployed truth, only when a session backs it. A missing session is stated,
  // never guessed around: "not checked" and "nothing there" are different facts.
  const deployed = live?.count ?? null
  const dc = drift?.counts ?? null

  const verdict = (() => {
    if (!summary) return null
    if (!pdc) return { ok: null, line: 'Authored and ready — no PDC session, so nothing about the live catalog is claimed here.' }
    if (!dc) return { ok: null, line: 'Live catalog was not readable; the deployed half of this report is missing.' }
    if (dc.missing === 0 && dc.drifted === 0 && dc.orphaned === 0) {
      return { ok: true, line: `Deployed and governed agree: ${dc.clean} method(s) clean, nothing drifted, nothing missing, nothing orphaned.` }
    }
    return {
      ok: false,
      line: `${dc.clean} clean · ${dc.drifted} drifted · ${dc.missing} missing · ${dc.orphaned} orphaned — deployed and governed do not agree.`,
    }
  })()

  // The last mile: deploy proves a method landed, drift proves it still matches
  // the contract, and neither notices a rule that deployed cleanly then never
  // fired. That only shows up on the columns.
  async function readBack() {
    const names = tables.split(/[\s,]+/).map((t) => t.trim()).filter(Boolean)
    if (!names.length) { setError('name at least one table to read back'); return }
    setBusy(true); setError(null)
    try { setIdent(await post('/api/pdc/identified', { tables: names, prefix })) }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  function exportHtml() {
    const esc = (x) => String(x ?? '').replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]))
    const rows = (o) => Object.entries(o).map(([k, v]) =>
      `<tr><td>${esc(k)}</td><td style="text-align:right">${v}</td></tr>`).join('')
    const html = `<!doctype html><meta charset="utf-8">
<title>Policy report — ${esc(summary.glossary)}</title>
<style>
 body{font:15px/1.6 system-ui,-apple-system,"Segoe UI",sans-serif;max-width:60rem;margin:2rem auto;padding:0 1.2rem;color:#16181d}
 h1{font-size:1.7rem;margin:0 0 .2rem} h2{font-size:1.15rem;margin:1.8rem 0 .5rem}
 .meta{color:#666;font-size:.9rem} table{border-collapse:collapse;width:100%;margin:.4rem 0}
 td,th{border-bottom:1px solid #e3e4e9;padding:.4rem .6rem;text-align:left}
 .v{padding:.8rem 1rem;border-left:3px solid ${verdict?.ok ? '#1a7346' : verdict?.ok === false ? '#a8251d' : '#8f5f00'};background:#f6f6f8;margin:1rem 0}
 code{background:#f0f1f4;padding:.1em .35em;border-radius:3px;font-size:.9em}
</style>
<h1>${esc(summary.glossary)} — Data Identification report</h1>
<p class="meta">${esc(summary.file)} · prefix <code>${esc(prefix)}</code> · compiled ${new Date().toLocaleString()}
${pdc ? ` · live: ${esc(pdc.username)} @ ${esc(pdc.base)}` : ' · no PDC session'}</p>
<div class="v"><b>${verdict?.ok === true ? 'In agreement' : verdict?.ok === false ? 'Divergence' : 'Offline report'}</b><br>${esc(verdict?.line)}</div>
<h2>The contract</h2>
<table><tr><td>Concepts</td><td style="text-align:right">${summary.concepts}</td></tr>
<tr><td>Seeded (authorable)</td><td style="text-align:right">${summary.seeded}</td></tr>
<tr><td>Term ids resolved</td><td style="text-align:right">${summary.resolved_term_ids} of ${summary.concepts}</td></tr>
<tr><td>Governed tags</td><td style="text-align:right">${summary.governed_tags}</td></tr>
<tr><td>Off-vocabulary tags</td><td style="text-align:right">${summary.off_vocabulary ?? 0}</td></tr></table>
<h2>Authored — ${authored} method(s)</h2>
<table><tr><td>Data Patterns</td><td style="text-align:right">${patterns.length}</td></tr>
<tr><td>Dictionaries</td><td style="text-align:right">${dicts.length}</td></tr>
<tr><td>Bound by term id</td><td style="text-align:right">${boundById} of ${authored}</td></tr></table>
<h2>What each method rests on</h2>
<table>${rows(evidence)}</table>
<h2>Not authored — ${(preview?.skipped ?? []).length} concept(s)</h2>
<table>${rows(skipGroups)}</table>
${dc ? `<h2>Deployed vs governed</h2><table>${rows(dc)}</table>` : ''}
<p class="meta">Written by the PDC Policy Generator. Every figure is read back from the
Registry, the authored set${dc ? ' and the live catalog' : ''} at compile time.</p>`
    const blob = new Blob([html], { type: 'text/html' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `policy-report-${(summary.glossary || 'registry').toLowerCase().replace(/\s+/g, '-')}.html`
    a.click()
    URL.revokeObjectURL(a.href)
  }

  if (!summary) return <p className="hint-line">Load a Registry first — the report is compiled from it.</p>

  return (
    <>
      <section className="card">
        <header>
          <h2>Report <span>{summary.glossary}</span></h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <label className="inline-field">prefix
              <input value={prefix} onChange={(e) => setPrefix(e.target.value)}
                     placeholder="Arizona" style={{ width: '8rem' }} />
            </label>
            <button className="primary" onClick={compile} disabled={busy}>
              {busy ? 'Compiling…' : '↻ Refresh'}
            </button>
            <button className="ghost" onClick={exportHtml} disabled={busy || !preview}>
              ⬇ Export standalone HTML
            </button>
          </div>
        </header>
        <p className="hint-line">
          One account of the whole pipeline: what the contract governs, what this app authored
          from it, and — when a session exists — what is actually live in PDC. Recompiled on
          demand from those three sources, never remembered.
          {stampedAt && <> Last compiled {stampedAt}.</>}
        </p>
        {error && <div className="error">{error}</div>}
        {verdict && (
          <p className={`summary ${verdict.ok === true ? 'ok' : verdict.ok === false ? 'warn' : ''}`}>
            {verdict.ok === true ? '✓ ' : verdict.ok === false ? '⚠ ' : 'ℹ '}{verdict.line}
          </p>
        )}
      </section>

      <section className="card">
        <h3 className="subhead">The contract</h3>
        <div className="tiles">
          <div className="tile"><div className="value">{summary.concepts}</div><div className="label">concepts</div></div>
          <div className="tile"><div className="value">{summary.seeded}</div><div className="label">seeded (authorable)</div></div>
          <div className="tile"><div className="value">{summary.resolved_term_ids}</div><div className="label">term ids resolved</div></div>
          <div className="tile"><div className="value">{summary.governed_tags}</div><div className="label">governed tags</div></div>
          <div className="tile"><div className="value">{summary.off_vocabulary ?? 0}</div><div className="label">off-vocabulary</div></div>
        </div>
        {(summary.unresolved_authorable?.length ?? 0) > 0 && (
          <p className="hint-line">
            ⚠ {summary.unresolved_authorable.length} authorable concept(s) still have no term id —
            their methods bind by name ({summary.unresolved_authorable.join(', ')}). Reconcile and
            Stamp ids fixes it; the stamp is in memory, so reconcile and deploy want the same
            session.
          </p>
        )}
        {(summary.unresolved_authorable?.length ?? 0) === 0
          && (summary.unresolved_link_governed?.length ?? 0) > 0 && (
          <p className="notes">
            {summary.unresolved_link_governed.length} unresolved concept(s) are link-governed —
            no method affected ({summary.unresolved_link_governed.join(', ')}).
          </p>
        )}
      </section>

      <section className="card">
        <h3 className="subhead">Authored from it — {authored} method(s)</h3>
        <div className="tiles">
          <div className="tile"><div className="value">{patterns.length}</div><div className="label">data patterns</div></div>
          <div className="tile"><div className="value">{dicts.length}</div><div className="label">dictionaries</div></div>
          <div className="tile"><div className="value">{boundById}</div><div className="label">bound by id ({pct(boundById, authored)})</div></div>
          <div className="tile"><div className="value">{(preview?.skipped ?? []).length}</div><div className="label">concepts not authored</div></div>
        </div>

        <h3 className="subhead">What each method rests on</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Evidence</th><th className="num">Methods</th><th className="num">Share</th><th>What it means</th></tr></thead>
            <tbody>
              {Object.entries(evidence).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                <tr key={k}>
                  <td><span className={`badge ${k === 'name-anchored' ? 'accent' : k === 'curated' ? 'neutral' : 'good'}`}>{k}</span></td>
                  <td className="num">{v}</td>
                  <td className="num">{pct(v, authored)}</td>
                  <td className="notes">{EVIDENCE_NOTE[k] ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {Object.keys(skipGroups).length > 0 && (
          <>
            <h3 className="subhead">Not authored, and why</h3>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Reason</th><th className="num">Concepts</th></tr></thead>
                <tbody>
                  {Object.entries(skipGroups).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <tr key={k}><td className="notes">{k}</td><td className="num">{v}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <header>
          <h2>Did the rules actually fire? <span>identification, read back</span></h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <input className="text" value={tables} onChange={(e) => setTables(e.target.value)}
                   placeholder="table names, e.g. customers water_quality_reports"
                   style={{ minWidth: '22rem' }} />
            <button className="ghost" onClick={readBack} disabled={busy || !pdc}>
              {busy ? 'Reading…' : '⇩ Read back'}
            </button>
          </div>
        </header>
        <p className="hint-line">
          Deploy proves a method landed and Drift proves it still matches the contract. Neither
          notices a rule that deployed cleanly and then never fired — that only shows on the
          columns. A <b>term</b> on a column proves nothing on its own, because the Glossary's
          Apply binds terms too; the method's <b>tags</b> are what a rule stamps when it actually
          matches, so those decide the verdict.
        </p>
        {ident && (
          <>
            <div className="chips-row">
              <span className="badge good">{ident.counts.expected_tagged} tagged as governed</span>
              <span className={`badge ${ident.counts.expected_term_only ? 'warning' : 'neutral'}`}>
                {ident.counts.expected_term_only ?? 0} term only (Apply, not a match)
              </span>
              <span className={`badge ${ident.counts.expected_missing ? 'warning' : 'neutral'}`}>
                {ident.counts.expected_missing} expected, nothing there
              </span>
              <span className="badge good"
                    title="No method claims these columns and the bound term is exactly the one the Registry maps there — the Glossary's Apply link governing by design (names, addresses, dates, free text)">
                {ident.counts.link_governed ?? 0} link-governed (by design)
              </span>
              <span className={`badge ${ident.counts.unexpected ? 'accent' : 'neutral'}`}
                    title="A term is bound that the Registry neither identifies NOR maps on this column — worth a look">
                {ident.counts.unexpected} unexpected
              </span>
              <span className="badge neutral">{ident.counts.untouched} untouched</span>
            </div>
            <div className="table-scroll" style={{ maxHeight: '420px', overflowY: 'auto' }}>
              <table>
                <thead><tr><th>Table</th><th>Column</th><th>Verdict</th><th>Contract expects</th><th>PDC bound</th><th>Tags on column</th></tr></thead>
                <tbody>
                  {ident.rows.filter((r) => r.verdict !== 'untouched').map((r) => (
                    <tr key={`${r.table}.${r.column}`}>
                      <td className="notes">{r.table}</td>
                      <td>{r.column}</td>
                      <td>
                        <span className={`badge ${['expected_tagged', 'link_governed'].includes(r.verdict) ? 'good'
                          : r.verdict === 'unexpected' ? 'accent' : 'warning'}`}
                              title={r.verdict === 'expected_term_only'
                                ? 'The term is bound but none of the method’s tags are on the column — that is a term link from the Glossary’s Apply, not a rule that matched'
                                : r.verdict === 'link_governed'
                                ? 'The Registry maps this exact term here and no method claims the column — the Apply link governing by design'
                                : undefined}>
                          {r.verdict.replaceAll('_', ' ')}
                        </span>
                      </td>
                      <td className="notes">{r.expected.join(', ') || '—'}</td>
                      <td className="notes">{r.bound.join(', ') || '—'}</td>
                      <td className="notes">{(r.tags ?? []).join(', ') || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      <section className="card">
        <h3 className="subhead">Live in PDC</h3>
        {!pdc ? (
          <p className="hint-line">
            No PDC session, so this half is unknown rather than empty. Connect on the Load page
            and refresh to have the report include the deployed set and the drift verdicts.
          </p>
        ) : (
          <>
            <div className="tiles">
              <div className="tile"><div className="value">{deployed ?? '—'}</div><div className="label">methods live under “{prefix}”</div></div>
              <div className="tile"><div className="value">{dc?.clean ?? '—'}</div><div className="label">clean</div></div>
              <div className="tile"><div className="value">{dc?.drifted ?? '—'}</div><div className="label">drifted</div></div>
              <div className="tile"><div className="value">{dc?.missing ?? '—'}</div><div className="label">missing</div></div>
              <div className="tile"><div className="value">{dc?.orphaned ?? '—'}</div><div className="label">orphaned</div></div>
            </div>
            <p className="hint-line">
              Read from <b>{pdc.username}</b> @ <b>{pdc.base}</b>. The method listing is paged, so
              these counts are the whole catalog rather than its first hundred rows.
            </p>
          </>
        )}
      </section>
    </>
  )
}
