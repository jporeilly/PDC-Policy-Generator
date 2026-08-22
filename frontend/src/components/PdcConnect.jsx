import { useState } from 'react'

/**
 * The PDC session card. It lived inside Reconcile until 1.10.3, which meant the
 * connection could only be made from a page you cannot open until a Registry is
 * loaded — a session dropped by a restart left no way back in. Connecting is a
 * setup act, not a reconcile act, so the same card now sits on Load as well.
 *
 * One card, one component: both copies read and write the App's single `pdc`
 * state, so connecting in either place lights up the whole workflow.
 */
export default function PdcConnect({ pdc, onPdc, hint }) {
  const [form, setForm] = useState({ base_url: '', username: '', password: '', token: '', verify_tls: false })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function connect() {
    setBusy(true)
    setError(null)
    try {
      const res = await fetch('/api/pdc/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      const data = await res.json()
      if (!res.ok) throw new Error(data.detail || res.statusText)
      onPdc(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
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
        {hint ?? 'The token lives in memory for this session only; the password is never stored.'}
      </p>
      {/* Generic placeholders only — a real estate host compiled into the UI
          is exactly the leak the sibling app's bundle guard exists for, and
          its release train once failed on a real host in a placeholder.
          tests/test_no_real_hosts.py enforces the same rule here. */}
      <div className="form-grid">
        <label>PDC Base URL
          <input placeholder="https://[PDC-SERVER URL]" value={form.base_url}
                 onChange={(e) => setForm({ ...form, base_url: e.target.value })} />
        </label>
        <label>PDC Username
          <input placeholder="PDC catalog user" value={form.username}
                 onChange={(e) => setForm({ ...form, username: e.target.value })} />
        </label>
        <label>PDC Password
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
  )
}
