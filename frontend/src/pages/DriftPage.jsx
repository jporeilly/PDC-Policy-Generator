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

    <VerdictsExplainer />
    </>
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
