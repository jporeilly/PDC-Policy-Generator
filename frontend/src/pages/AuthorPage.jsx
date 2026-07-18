import { useCallback, useEffect, useState } from 'react'
import { SummaryCard } from './LoadPage.jsx'

const BUCKETS = {
  seed: { label: 'Needs a detection seed', cls: 'warning', icon: '⚠',
          hint: 'Identifiable data (SSN, email, phone…) whose scan produced no seed — re-scan or add one glossary-side.' },
  mapping_only: { label: 'Mapping-only by steward decision', cls: 'neutral', icon: '·',
                  hint: 'The Registry carries detection_intent: mapping_only — the steward decided no detectable shape exists; the Apply step governs these.' },
  structural: { label: 'Structural — correctly method-less', cls: 'neutral', icon: '·',
                hint: 'Record/report/summary concepts describe containers, not values; no method should exist.' },
  rule: { label: 'Free text — needs a vocabulary rule', cls: 'accent', icon: 'ℹ',
          hint: 'Notes/description fields have no stable shape; identify with vocabulary dictionaries or rules.' },
  mapping: { label: 'Govern by mapping', cls: 'neutral', icon: '·',
             hint: 'Term-to-column mapping (not identification) is the governance mechanism here.' },
}

// The 1.5.x "What these groups mean" legend, in the suite's expandable
// explainer pattern (details.card > summary, collapsed by default): a
// skipped concept is not ungoverned — a different mechanism owns it.
function SkippedGroupsExplainer() {
  return (
    <details className="card" style={{ marginTop: '.6rem' }}>
      <summary>What these groups mean — why a skipped concept is still governed</summary>
      <p className="hint-line">
        Identification methods only make sense for values with a stable, recognizable
        shape. Everything else is governed by a different mechanism — the buckets name
        which one:
      </p>
      <ul className="workcycle">
        <li>
          <b>⚠ Needs a detection seed</b> — identifiable data (SSN, email, phone…) whose
          scan produced no seed. Fix it glossary-side: re-scan, or add a curated seed to
          the domain pack, then re-export the Registry. The only amber bucket — the only
          one that wants action here. <b>⇪ Export seed request</b> writes
          <code> seed-request.json</code> beside the loaded Registry, so the Glossary
          steward sees exactly which terms still need one — the loop closes without
          re-typing anything.
        </li>
        <li>
          <b>· Mapping-only by steward decision</b> — the Registry's optional
          <code> detection_intent: "mapping_only"</code> field records an explicit
          steward call: no detectable shape exists, so the Apply step's term, tags and
          sensitivity stamps on the mapped columns are the whole governance story.
          Not a warning — the question was asked and answered.
        </li>
        <li>
          <b>· Structural — correctly method-less</b> — record/report/summary concepts
          describe containers, not values; no method <i>should</i> exist.
        </li>
        <li>
          <b>ℹ Free text — needs a vocabulary rule</b> — notes and description fields
          have no stable shape; vocabulary dictionaries or business rules govern them.
        </li>
        <li>
          <b>· Govern by mapping</b> — the Glossary app's Apply step already stamps term,
          tags and sensitivity onto the steward-mapped columns; identification would add
          nothing.
        </li>
      </ul>
    </details>
  )
}

export default function AuthorPage({ summary }) {
  const [prefix, setPrefix] = useState('')
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)
  const [seedBusy, setSeedBusy] = useState(false)
  const [seedMsg, setSeedMsg] = useState(null)   // {ok, text}

  const runPreview = useCallback(async (p) => {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefix: p || null }),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setPreview(body)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => { runPreview(prefix) }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  async function download() {
    const res = await fetch('/api/author', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefix: prefix || null }),
    })
    if (!res.ok) return
    const blob = await res.blob()
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = (res.headers.get('Content-Disposition')?.match(/filename="?([^";]+)/)?.[1])
      ?? 'data-identification.zip'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  const skippedByBucket = {}
  for (const s of preview?.skipped ?? []) {
    (skippedByBucket[s.bucket] ??= []).push(s)
  }

  // The no-seed loop's return channel: write seed-request.json beside the
  // loaded Registry so the Glossary app can discover which terms still
  // need a detection seed.
  async function exportSeedRequest() {
    const terms = (skippedByBucket.seed ?? []).map((s) => s.term)
    setSeedBusy(true)
    setSeedMsg(null)
    try {
      const res = await fetch('/api/seed-request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ terms }),
      })
      const body = await res.json()
      if (!res.ok) throw new Error(body.detail || res.statusText)
      setSeedMsg({ ok: true,
                   text: `✓ ${body.file} written beside the Registry (${body.terms} term${body.terms === 1 ? '' : 's'}) — the Glossary app can pick it up` })
    } catch (err) {
      setSeedMsg({ ok: false, text: err.message })
    } finally {
      setSeedBusy(false)
    }
  }

  return (
    <>
      <SummaryCard summary={summary} />

      <section className="card">
        <header>
          <h2>
            Author Data Identification methods
            {preview && <span>prefix: {preview.prefix}</span>}
          </h2>
          <div className="actions" style={{ marginTop: 0 }}>
            <input className="text" placeholder="Name prefix (default: glossary name)"
                   value={prefix} onChange={(e) => setPrefix(e.target.value)} />
            <button className="ghost" onClick={() => runPreview(prefix)} disabled={busy}>
              {busy ? 'Previewing…' : '↻ Preview'}
            </button>
            <button className="primary" onClick={download} disabled={!preview}>
              ⬇ Download import zip
            </button>
          </div>
        </header>
        <p className="hint-line">
          Deterministic and offline: every regex and reference list below was induced from
          profiled data by the Glossary scan and travels inside the Registry. The zip is in
          the exact layout PDC 11's own Export produces — review before importing.
        </p>
        {error && <div className="error">{error}</div>}

        {preview && (
          <>
            <h3 className="subhead">Data Patterns ({preview.patterns.length})</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>Method</th><th>Term</th><th>Bound</th><th>Content regex</th>
                      <th>Signature</th><th>Column hint</th><th>Tags</th></tr>
                </thead>
                <tbody>
                  {preview.patterns.map((p) => (
                    <tr key={p.name}>
                      <td>{p.name}</td>
                      <td>{p.term}</td>
                      <td>{p.term_id
                        ? <span className="badge good" title={p.term_id}>✓ by id</span>
                        : <span className="badge warning" title="Reconcile to bind by id">⚠ by name</span>}</td>
                      <td className="mono cell-clip" title={p.regex}>{p.regex}</td>
                      <td className="mono cell-clip" title={p.signature ?? ''}>{p.signature ?? '—'}</td>
                      <td className="mono cell-clip" title={p.column_hint ?? ''}>{p.column_hint ?? '—'}</td>
                      <td className="notes">{p.tags.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <h3 className="subhead">Dictionaries ({preview.dictionaries.length})</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>Method</th><th>Term</th><th>Bound</th><th className="num">Values</th>
                      <th>Sample</th><th>Column hint</th><th>Tags</th></tr>
                </thead>
                <tbody>
                  {preview.dictionaries.map((d) => (
                    <tr key={d.name}>
                      <td>{d.name}</td>
                      <td>{d.term}</td>
                      <td>{d.term_id
                        ? <span className="badge good" title={d.term_id}>✓ by id</span>
                        : <span className="badge warning" title="Reconcile to bind by id">⚠ by name</span>}</td>
                      <td className="num">{d.values_count}</td>
                      <td className="notes cell-clip" title={d.values.slice(0, 12).join(', ')}>
                        {d.values.slice(0, 5).join(', ')}{d.values_count > 5 ? '…' : ''}
                      </td>
                      <td className="mono cell-clip" title={d.column_hint ?? ''}>{d.column_hint ?? '—'}</td>
                      <td className="notes">{d.tags.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {preview.skipped.length > 0 && (
              <>
                <h3 className="subhead">Skipped concepts ({preview.skipped.length}) — grouped by governance mechanism</h3>
                <SkippedGroupsExplainer />
                {Object.entries(BUCKETS).map(([key, b]) => {
                  const items = skippedByBucket[key]
                  if (!items?.length) return null
                  return (
                    <div className="bucket-group" key={key}>
                      <div className="bucket-title">
                        <span className={`badge ${b.cls}`}>{b.icon} {b.label} · {items.length}</span>
                        <span className="notes">{b.hint}</span>
                      </div>
                      <ul className="bucket-list">
                        {items.map((s) => (
                          <li key={s.term}>
                            {s.term} <span className="notes">— {s.why}</span>
                            {key === 'seed' && (
                              <span className="notes"> · will be listed in seed-request.json</span>
                            )}
                          </li>
                        ))}
                      </ul>
                      {key === 'seed' && (
                        <div className="actions" style={{ marginTop: '.5rem' }}>
                          <button className="ghost" onClick={exportSeedRequest} disabled={seedBusy}>
                            {seedBusy ? 'Writing…' : '⇪ Export seed request'}
                          </button>
                          {seedMsg && (
                            <span className={seedMsg.ok ? 'ok' : 'warn'} style={{ fontSize: '.84rem' }}>
                              {seedMsg.text}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  )
                })}
              </>
            )}
          </>
        )}
      </section>
    </>
  )
}
