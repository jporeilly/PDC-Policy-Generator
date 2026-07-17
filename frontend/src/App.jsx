import { useEffect, useState } from 'react'
import DocModal from './components/DocModal.jsx'
import ThemeSelect from './components/ThemeSelect.jsx'
import LoadPage from './pages/LoadPage.jsx'
import AuthorPage from './pages/AuthorPage.jsx'
import ReconcilePage from './pages/ReconcilePage.jsx'

const STEPS = [
  { label: 'Load', hint: 'Classification Registry',
    tip: 'Load the Registry the Glossary Generator exported — the contract this app authors from.' },
  { label: 'Author', hint: 'patterns & dictionaries',
    tip: 'Preview and download import-ready PDC Data Identification methods. Deterministic and offline — every regex and list came from the Registry.' },
  { label: 'Reconcile', hint: 'bind ids to live PDC',
    tip: 'Verify each concept’s term id against a live PDC, bind by id, and manage the imported method set.' },
]

export default function App() {
  const [step, setStep] = useState(0)
  const [summary, setSummary] = useState(null)   // loaded Registry summary
  const [version, setVersion] = useState('')
  const [showChangelog, setShowChangelog] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  useEffect(() => {
    fetch('/api/version')
      .then((r) => r.json())
      .then((v) => setVersion(v.version))
      .catch(() => {})
  }, [])

  const maxStep = summary ? 2 : 0

  return (
    <div className="app">
      <header className="masthead">
        <h1>
          Policy <em>Generator</em>
          {version && (
            <button className="version" onClick={() => setShowChangelog(true)}
                    title="What's new — view the changelog">
              v{version}
            </button>
          )}
        </h1>
        <span className="links">
          Classification Registry → PDC Data Identification ·{' '}
          <a href="/docs" target="_blank" rel="noreferrer">API docs</a> ·{' '}
          <button className={`nav${showSettings ? ' active' : ''}`}
                  onClick={() => setShowSettings(!showSettings)}>
            ⚙ Settings
          </button>
        </span>
      </header>
      {showChangelog && (
        <DocModal title="Changelog" url="/changelog" onClose={() => setShowChangelog(false)} />
      )}

      {showSettings ? (
        <SettingsView onBack={() => setShowSettings(false)} version={version} />
      ) : (
        <>
          <p className="tagline">
            The second half of the governance pipeline: what PDC identifies can never
            quietly diverge from what the glossary governs.
          </p>
          <ol className="stepper">
            {STEPS.map((s, i) => {
              const state = i < step ? 'done' : i === step ? 'active' : i <= maxStep ? 'ready' : 'locked'
              return (
                <li key={s.label} className={state}>
                  <button disabled={i > maxStep} onClick={() => setStep(i)} title={s.tip}
                          aria-current={i === step ? 'step' : undefined}>
                    <span className="dot">{i < step ? '✓' : i + 1}</span>
                    <span className="step-text">
                      <span className="step-label">{s.label}</span>
                      <span className="step-hint">{s.hint}</span>
                    </span>
                  </button>
                  {i < STEPS.length - 1 && <span className="bar" aria-hidden="true" />}
                </li>
              )
            })}
          </ol>

          {step === 0 && (
            <LoadPage
              summary={summary}
              onLoaded={(s) => { setSummary(s); setStep(1) }}
            />
          )}
          {step === 1 && summary && <AuthorPage summary={summary} />}
          {step === 2 && summary && (
            <ReconcilePage summary={summary} onSummary={setSummary} />
          )}
        </>
      )}
    </div>
  )
}

function SettingsView({ onBack, version }) {
  return (
    <div className="settings">
      <button className="ghost back-btn" onClick={onBack}>← Back to workflow</button>
      <section className="card">
        <h2>Appearance</h2>
        <div className="form-grid">
          <label>
            Color theme
            <ThemeSelect />
          </label>
        </div>
      </section>
      <section className="card">
        <h2>About</h2>
        <dl>
          <dt>Version</dt><dd>{version}</dd>
          <dt>Service</dt><dd>PDC Policy Generator — local-first, single user</dd>
          <dt>Contract</dt><dd>classification-registry/1 (see docs/CONTRACT.md)</dd>
          <dt>PDC</dt><dd>validated against Pentaho Data Catalog 11.0.0 (public API v3)</dd>
        </dl>
      </section>
    </div>
  )
}
