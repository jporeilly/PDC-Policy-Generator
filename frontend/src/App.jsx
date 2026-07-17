import { useEffect, useState } from 'react'
import DocModal from './components/DocModal.jsx'
import ThemeSelect from './components/ThemeSelect.jsx'
import LoadPage from './pages/LoadPage.jsx'
import AuthorPage from './pages/AuthorPage.jsx'
import ReconcilePage from './pages/ReconcilePage.jsx'
import DeployPage from './pages/DeployPage.jsx'
import DriftPage from './pages/DriftPage.jsx'

/* Nav icons — the suite's shared visual family (24 viewBox, 1.7 stroke),
   same set style as PDC-Insights' shell. */
const ICONS = {
  load: <path d="M3.5 7a2 2 0 0 1 2-2h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2V7Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" fill="none" />,
  author: <><path d="m4 20 4-1 10-10-3-3L5 16l-1 4Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" fill="none" /><path d="m14 6 4 4" stroke="currentColor" strokeWidth="1.7" fill="none" /></>,
  reconcile: <><path d="M10.6 13.4a4.3 4.3 0 0 0 6.1 0l2.8-2.8a4.3 4.3 0 0 0-6.1-6.1L11.7 6.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /><path d="M13.4 10.6a4.3 4.3 0 0 0-6.1 0l-2.8 2.8a4.3 4.3 0 0 0 6.1 6.1l1.7-1.7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /></>,
  deploy: <><path d="M12 15V4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /><path d="m7.5 8.5 4.5-4 4.5 4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" /><path d="M4.5 14.5V17a2.5 2.5 0 0 0 2.5 2.5h10a2.5 2.5 0 0 0 2.5-2.5v-2.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /></>,
  drift: <><path d="M12 4v16M8.5 20h7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /><path d="M12 6H6l-2.5 5a3 3 0 0 0 5 0L6 6m12 0h-6m6 0 -2.5 5a3 3 0 0 0 5 0L18 6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" /></>,
  settings: <><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.7" fill="none" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9l2.1 2.1m10 10 2.1 2.1M19.1 4.9 17 7m-10 10-2.1 2.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /></>,
}

function Ico({ id }) {
  return <svg className="nav-ico" viewBox="0 0 24 24">{ICONS[id]}</svg>
}

const STEPS = [
  { id: 'load', label: 'Load', hint: 'Classification Registry',
    tip: 'Load the Registry the Glossary Generator exported — the contract this app authors from.' },
  { id: 'author', label: 'Author', hint: 'patterns & dictionaries',
    tip: 'Preview and download import-ready PDC Data Identification methods. Deterministic and offline — every regex and list came from the Registry.' },
  { id: 'reconcile', label: 'Reconcile', hint: 'bind ids to live PDC',
    tip: 'Verify each concept’s term id against a live PDC, bind by id, and manage the imported method set.' },
  { id: 'deploy', label: 'Deploy', hint: 'import the set into PDC',
    tip: 'Import the authored set into PDC over the import API, verify every method landed, and re-stamp the reconciled term ids. Needs a connected PDC and reconciled ids.' },
  { id: 'drift', label: 'Drift', hint: 'deployed vs governed',
    tip: 'Compare every deployed method against the Registry: tags, term bindings, regexes, dictionary counts. Needs a loaded Registry and a PDC session.' },
]

export default function App() {
  const [step, setStep] = useState(0)
  const [summary, setSummary] = useState(null)   // loaded Registry summary
  const [pdc, setPdc] = useState(null)           // live PDC session (from Reconcile)
  const [version, setVersion] = useState('')
  const [showChangelog, setShowChangelog] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  useEffect(() => {
    fetch('/api/version')
      .then((r) => r.json())
      .then((v) => setVersion(v.version))
      .catch(() => {})
  }, [])

  // Per-step gates, consistent with the ones the pages enforce server-side:
  // Author/Reconcile need a Registry; Deploy additionally needs a PDC session
  // and at least one reconciled term id; Drift needs Registry + PDC session.
  const stepReady = [
    true,
    !!summary,
    !!summary,
    !!summary && !!pdc && (summary.resolved_term_ids ?? 0) > 0,
    !!summary && !!pdc,
  ]
  const crumbGroup = showSettings ? 'Configure' : 'Workflow'
  const crumbLabel = showSettings ? 'Settings' : STEPS[step].label

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
              <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3Z"
                    stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
              <path d="m9 12 2 2 4-4"
                    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="brand-name">Policy <em>Generator</em></div>
            <div className="brand-sub">Pentaho Data Catalog</div>
          </div>
          {version && (
            <button className="version-pill" onClick={() => setShowChangelog(true)}
                    title="What's new — view the changelog">
              v{version}
            </button>
          )}
        </div>

        <nav className="nav">
          <div className="nav-label">Workflow</div>
          {STEPS.map((s, i) => (
            <button key={s.id}
                    className={`nav-item${!showSettings && step === i ? ' active' : ''}`}
                    disabled={!stepReady[i]} title={s.tip}
                    onClick={() => { setShowSettings(false); setStep(i) }}
                    aria-current={!showSettings && step === i ? 'page' : undefined}>
              <Ico id={s.id} />{s.label}
            </button>
          ))}
          <div className="nav-label">Configure</div>
          <button className={`nav-item${showSettings ? ' active' : ''}`}
                  title="Appearance and build information"
                  onClick={() => setShowSettings(true)}
                  aria-current={showSettings ? 'page' : undefined}>
            <Ico id="settings" />Settings
          </button>
        </nav>

        <div className="side-foot">
          <div className="conn"
               title={pdc
                 ? `Connected to ${pdc.base}${pdc.roles?.length ? ` · roles: ${pdc.roles.join(', ')}` : ''}`
                 : 'No live PDC session — connect on the Reconcile page'}>
            <span className={`dot ${pdc ? 'ok' : 'warn'}`} aria-hidden="true" />
            {pdc
              ? <>PDC&nbsp;·&nbsp;<span className="mono">{pdc.username ?? pdc.base}</span></>
              : <>PDC&nbsp;·&nbsp;not connected</>}
          </div>
          <div className="conn" title="The interactive OpenAPI docs for this app's backend">
            API&nbsp;·&nbsp;<a className="mono" href="/docs" target="_blank" rel="noreferrer">docs</a>
          </div>
          <ThemeSelect />
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumb">{crumbGroup}&nbsp;/&nbsp;<b>{crumbLabel}</b></div>
          <div className="topbar-spacer" />
        </header>

        <div className="content">
          {showSettings ? (
            <SettingsView version={version} />
          ) : (
            <>
              <p className="tagline">
                The second half of the governance pipeline: what PDC identifies can never
                quietly diverge from what the glossary governs.
              </p>
              <ol className="stepper">
                {STEPS.map((s, i) => {
                  const state = i < step ? 'done' : i === step ? 'active' : stepReady[i] ? 'ready' : 'locked'
                  return (
                    <li key={s.label} className={state}>
                      <button disabled={!stepReady[i]} onClick={() => setStep(i)} title={s.tip}
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
                <ReconcilePage summary={summary} onSummary={setSummary}
                               pdc={pdc} onPdc={setPdc} />
              )}
              {step === 3 && summary && (
                <DeployPage summary={summary} pdc={pdc} onPdc={setPdc} />
              )}
              {step === 4 && summary && (
                <DriftPage summary={summary} pdc={pdc} onPdc={setPdc} />
              )}
            </>
          )}
        </div>
      </div>

      {showChangelog && (
        <DocModal title="Changelog" url="/changelog" onClose={() => setShowChangelog(false)} />
      )}
    </div>
  )
}

function SettingsView({ version }) {
  return (
    <div className="settings">
      <div className="page-head">
        <div>
          <h1>Settings</h1>
          <p>Appearance and build information for the Policy Generator.</p>
        </div>
      </div>
      <div className="set-grid">
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
    </div>
  )
}
