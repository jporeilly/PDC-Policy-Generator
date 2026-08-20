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

// What a method rests on. Not decoration: a profiled shape was induced from the
// estate's own values, while a name-anchored rule exists because a steward
// declared the column NAME authoritative for a concept whose values carry no
// identifying shape (a date, a bounded measure). Same table, different strength
// of claim — the reviewer is entitled to see which is which.
const EVIDENCE = {
  profiled: { cls: 'good', label: 'profiled',
              hint: 'Induced from the estate’s own values by the Glossary scan.' },
  recognised: { cls: 'good', label: 'recognised',
                hint: 'The profiler matched a known kind (email, phone, …) in this estate’s data; the shape is the profiler’s own.' },
  curated: { cls: 'neutral', label: 'curated',
             hint: 'A vetted seed from the versioned domain pack — the baseline for concepts profiling cannot induce.' },
  'name-anchored': { cls: 'accent', label: 'name-anchored',
                     hint: 'The steward flipped a mapping-only concept to Auto: the column NAME carries identity and the content regex is only a sanity check. Fires only when name AND shape agree.' },
}

function EvidenceBadge({ kind }) {
  const e = EVIDENCE[kind] || EVIDENCE.profiled
  return <span className={`badge ${e.cls}`} title={e.hint}>{e.label}</span>
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

  // A column that can only ever print "—" is noise. This estate's scan carries
  // no position signatures at all, so the header appears only when at least one
  // authored rule actually has one to show.
  const anySignature = (preview?.patterns ?? []).some((p) => p.signature)

  return (
    <>
      <details className="card" open>
        <summary>What this page does — and what to do on it</summary>
        <p className="hint-line">
          Authoring turns each governed row of the Registry into an import-ready PDC method:
          a <b>Data Pattern</b> where the concept has a value shape, a <b>Dictionary</b> where it
          has a reference list. Nothing is decided here and nothing is editable — every regex,
          value list, tag and term binding is copied from the contract the Glossary wrote. Change
          what you see by changing the glossary, not by hand-editing a rule.
        </p>
        <ol className="workcycle">
          <li>
            <b>Set the name prefix</b> (defaults to the glossary name). Every method is named
            <code> prefix + term</code>, and that prefix is the scope Deploy, Drift and Retire
            all work in — it is what lets this app clean up exactly what it created.
          </li>
          <li>
            <b>Preview</b>, then read two columns before anything else: <b>Bound</b> and
            <b>Evidence</b>. They tell you how strong each method is.
          </li>
          <li>
            <b>Fix what those columns reveal, glossary-side</b> — a term binding by name wants a
            Reconcile; a concept in the skipped list wants a seed, a re-scan, or an honest
            mapping-only declaration.
          </li>
          <li>
            <b>Then either</b> ⬇ <b>Download import zip</b> and import it by hand in PDC
            (Data Operations → Data Identification → Import), <b>or</b> carry on to Reconcile and
            let <b>Deploy</b> push the same set over the API and bind the term ids for you.
            The zip and the deploy author byte-identical rules.
          </li>
        </ol>
        <h3 className="subhead">What the columns mean</h3>
        <div className="table-scroll">
          <table>
            <thead><tr><th>Column</th><th>Reading it</th></tr></thead>
            <tbody>
              <tr><td><b>Method</b></td><td className="notes">The name PDC will show, and the scope handle: <code>prefix + term</code>.</td></tr>
              <tr><td><b>Bound</b></td><td className="notes"><span className="badge good">✓ by id</span> the method carries PDC's own term id — the strong binding. <span className="badge warning">⚠ by name</span> it carries only the term's name, which breaks the moment a term is renamed. Reconcile turns the second into the first.</td></tr>
              <tr><td><b>Evidence</b></td><td className="notes">What the rule rests on. <b>profiled</b> and <b>recognised</b> come from the estate's own values; <b>curated</b> from the versioned domain pack; <b>name-anchored</b> is a steward's decision that the column NAME identifies the concept, with the regex only sanity-checking. They are not equally strong claims, which is why the column exists.</td></tr>
              <tr><td><b>Content regex</b></td><td className="notes">The shape PDC matches values against. For a name-anchored rule this is deliberately loose — it proves the column still holds numbers or dates, not that the column is the concept.</td></tr>
              <tr><td><b>Column hint</b></td><td className="notes">The column-name pattern, built from the physical columns the scan actually saw. It carries half the confidence on a name-anchored rule and a third on a profiled one.</td></tr>
              <tr><td><b>Tags</b></td><td className="notes">What the method stamps when it matches — filtered to the Registry's governed allow-list, so a method can never apply vocabulary the glossary does not govern.</td></tr>
              <tr><td><b>Values</b> / <b>Sample</b></td><td className="notes">Dictionaries only: how many reference values travel in the CSV, and the first few of them.</td></tr>
            </tbody>
          </table>
        </div>
      </details>

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
          Deterministic and offline: every regex, reference list and steward decision below
          travels inside the Registry — nothing is re-decided here. The <b>Evidence</b> column
          says what each method rests on, because they are not equally strong claims. The zip is
          in the exact layout PDC 11's own Export produces — review before importing.
        </p>
        {error && <div className="error">{error}</div>}

        {preview?.ambiguous_shapes?.length > 0 && (
          <div className="error" style={{ background: 'transparent' }}>
            <b>⚠ {preview.ambiguous_shapes.length} content shape(s) are claimed by more than one
            method.</b> A regex that identifies several concepts identifies none of them — on this
            estate one induced shape backed eight concepts and a free-text column came back bound
            to all eight. Fix it glossary-side (a real shape per concept, or declare them
            mapping-only); a Registry from 1.38.34 onward marks these name-anchored so the column
            name has to agree.
            <div className="table-scroll" style={{ marginTop: '.5rem', maxHeight: '180px', overflowY: 'auto' }}>
              <table>
                <thead><tr><th>Shape</th><th className="num">Methods</th><th>Claimed by</th></tr></thead>
                <tbody>
                  {preview.ambiguous_shapes.map((a) => (
                    <tr key={a.regex}>
                      <td className="mono cell-clip" title={a.regex}>{a.regex}</td>
                      <td className="num">{a.terms.length}</td>
                      <td className="notes">{a.terms.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
        {preview && (
          <>
            <h3 className="subhead">Data Patterns ({preview.patterns.length})</h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr><th>Method</th><th>Term</th><th>Bound</th><th>Evidence</th>
                      <th>Content regex</th>
                      {anySignature && <th>Signature</th>}
                      <th>Column hint</th><th>Tags</th></tr>
                </thead>
                <tbody>
                  {preview.patterns.map((p) => (
                    <tr key={p.name}>
                      <td>{p.name}</td>
                      <td>{p.term}</td>
                      <td>{p.term_id
                        ? <span className="badge good" title={p.term_id}>✓ by id</span>
                        : <span className="badge warning" title="Reconcile to bind by id">⚠ by name</span>}</td>
                      <td><EvidenceBadge kind={p.evidence} /></td>
                      <td className="mono cell-clip" title={p.regex}>{p.regex}</td>
                      {anySignature && (
                        <td className="mono cell-clip" title={p.signature ?? ''}>{p.signature ?? '—'}</td>
                      )}
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
                  <tr><th>Method</th><th>Term</th><th>Bound</th><th>Evidence</th>
                      <th className="num">Values</th>
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
                      <td><EvidenceBadge kind={d.evidence} /></td>
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
