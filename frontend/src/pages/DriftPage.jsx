import { useState } from 'react'

/* Drift-check — every deployed method under the prefix compared against the
   loaded Registry's governed facts. Verdicts rendered reconcile-style. */

const VERDICT = {
  clean: { cls: 'good', icon: '✓', tip: 'Every governed fact matches the Registry' },
  drifted: { cls: 'warning', icon: '⚠', tip: 'Deployed, but a governed fact diverged — see findings' },
  orphaned: { cls: 'accent', icon: 'ℹ', tip: 'Carries the prefix but the Registry no longer authors it' },
  missing: { cls: 'serious', icon: '✋', tip: 'The Registry authors it but it is not deployed' },
}

export default function DriftPage({ summary, pdc, onPdc }) {
  const [prefix, setPrefix] = useState('')
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/pdc/drift', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefix: prefix || null }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setOut(data)
    } catch (err) {
      setError(err.message)
      if (err.message.includes('expired')) onPdc(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
    <section className="card">
      <header>
        <h2>
          Drift-check deployed methods
          {out && <span>prefix: {out.prefix}</span>}
          {pdc && (
            <span className="badge good" title={`roles: ${(pdc.roles ?? []).join(', ')}`}>
              ✓ {pdc.username ?? 'connected'} @ {pdc.base}
            </span>
          )}
        </h2>
        <div className="actions" style={{ marginTop: 0 }}>
          <input className="text" placeholder="Name prefix (default: glossary name)"
                 value={prefix} onChange={(e) => setPrefix(e.target.value)} />
          <button className="primary" onClick={run} disabled={busy || !pdc}>
            {busy ? 'Checking…' : '⚖ Run drift-check'}
          </button>
        </div>
      </header>
      <p className="hint-line">
        Reads every deployed method under the prefix and compares it against the
        Registry: governed tags vs the allow-list, term binding (name + id), content
        regex and profile signature vs the seeds, dictionary row counts (PDC does not
        expose dictionary values, so the count is the proxy). What PDC identifies can
        never quietly diverge from what the glossary governs — this page is the proof.
      </p>
      {error && <div className="error">{error}</div>}

      {out && (
        <p className="summary">
          {Object.entries(VERDICT).map(([k, v]) => (
            <span key={k} title={v.tip} style={{ marginRight: '1rem' }}>
              <span className={`badge ${v.cls}`}>{v.icon} {k} {out.counts[k]}</span>
            </span>
          ))}
        </p>
      )}
      {out?.rows?.length === 0 && (
        <p className="summary"><span className="notes">
          Nothing deployed under this prefix and nothing authored — deploy first, or
          check the prefix.
        </span></p>
      )}
      {out?.rows?.length > 0 && (
        <div className="table-scroll" style={{ maxHeight: '460px', overflowY: 'auto' }}>
          <table>
            <thead>
              <tr><th>Method</th><th>Kind</th><th>Term</th><th>Verdict</th><th>Findings</th></tr>
            </thead>
            <tbody>
              {out.rows.map((r) => {
                const v = VERDICT[r.verdict]
                return (
                  <tr key={`${r.kind}:${r.name}`}>
                    <td>{r.name}</td>
                    <td className="notes">{r.kind}</td>
                    <td>{r.term ?? '—'}</td>
                    <td><span className={`badge ${v.cls}`} title={v.tip}>{v.icon} {r.verdict}</span></td>
                    <td className="notes">
                      {r.findings?.length
                        ? r.findings.map((f) => <div key={f}>{f}</div>)
                        : r.verdict === 'clean'
                          ? `${r.checks?.length ?? 0} checks passed`
                          : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>

    <EfficacyCard pdc={pdc} onPdc={onPdc} prefix={prefix} />

    <VerdictsExplainer />
    </>
  )
}

/* Efficacy — the third instrument (spec backlog 5). Re-profiling reads the
   DATA; drift reads the DEPLOYMENT; this joins them: does each method still
   match anything in the stored profile identification actually scores
   against? A method whose data moved underneath it reports drift-CLEAN and
   fires never — this is the only view that says so. */
const EFF = {
  live: { cls: 'good', icon: '✓', label: 'live' },
  dead: { cls: 'serious', icon: '✋', label: 'dead' },
  no_samples: { cls: 'warning', icon: '⚠', label: 'no samples' },
  unresolved: { cls: 'accent', icon: 'ℹ', label: 'unresolved' },
}

function EfficacyCard({ pdc, onPdc, prefix }) {
  const [out, setOut] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/pdc/efficacy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prefix: prefix || null }),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      setOut(data)
    } catch (err) {
      setError(err.message)
      if (err.message.includes('expired')) onPdc(null)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <header>
        <h2>Do the rules still match the data? <span>efficacy — seeds vs the stored profile</span></h2>
        <div className="actions" style={{ marginTop: 0 }}>
          <button className="primary" onClick={run} disabled={busy || !pdc}>
            {busy ? 'Joining…' : '⚗ Run efficacy check'}
          </button>
        </div>
      </header>
      <p className="hint-line">
        Drift proves a method still matches the <b>contract</b>; this proves it still matches
        the <b>data</b> — each authored seed evaluated against the stored profile samples
        identification actually scores with. A method whose data moved underneath it is
        drift-clean and fires never; it shows here as <b>dead</b>, with the values that
        replaced its shape. <b>No samples</b> means the profile retained nothing —
        re-profile before trusting any score on that column.
      </p>
      {error && <p className="summary warn">{error}</p>}
      {out && (
        <>
          <div className="chips-row">
            {Object.entries(EFF).map(([k, v]) => (
              <span key={k} className={`badge ${out.counts[k] ? v.cls : 'neutral'}`}>
                {v.icon} {v.label} {out.counts[k]}
              </span>
            ))}
          </div>
          <div className="table-scroll" style={{ maxHeight: '380px', overflowY: 'auto' }}>
            <table>
              <thead><tr><th>Method</th><th>Kind</th><th>Source</th><th>Match</th><th>Verdict</th><th>Notes</th></tr></thead>
              <tbody>
                {out.rows.map((r) => {
                  const v = EFF[r.verdict]
                  return (
                    <tr key={r.method}>
                      <td>{r.method}</td>
                      <td className="notes">{r.kind}</td>
                      <td className="notes">{r.source ?? '—'}</td>
                      <td className="num">{r.samples != null ? `${r.matched}/${r.samples}` : '—'}</td>
                      <td><span className={`badge ${v.cls}`}>{v.icon} {v.label}</span></td>
                      <td className="notes">{r.detail ?? '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}

// How to read the four verdicts — the suite's expandable explainer pattern
// (details.card > summary, collapsed by default).
function VerdictsExplainer() {
  return (
    <details className="card">
      <summary>Under the hood — reading the verdicts</summary>
      <ul className="workcycle">
        <li>
          <b>✓ clean</b> — every governed fact matches the Registry: tags on the
          allow-list, term bound by name and id, regex and signature as seeded,
          dictionary row count intact, method enabled.
        </li>
        <li>
          <b>⚠ drifted</b> — deployed, but a governed fact diverged (edited regex,
          off-vocabulary tag, broken term binding, changed row count, disabled method).
          The findings column names exactly what.
        </li>
        <li>
          <b>ℹ orphaned</b> — carries the prefix but the Registry no longer authors it:
          the concept was retired or renamed glossary-side. A candidate for the scoped
          Retire.
        </li>
        <li>
          <b>✋ missing</b> — the Registry authors it but PDC doesn't have it: never
          deployed, or deleted in PDC. Re-deploy restores it.
        </li>
      </ul>
      <p className="hint-line">
        The fix always flows one way: correct the fact glossary-side (or re-deploy), never
        hand-edit the deployed method — the Registry is the source of truth this page
        measures against.
      </p>
    </details>
  )
}
