// The five-stage workflow map — pure inline SVG, no chart libraries, and the
// same shape and class names as the Glossary's components/WorkflowDiagram.jsx
// so the two apps read as one suite. Every stage box is a real page and
// navigates via onNavigate(stepId); the two chips are things OUTSIDE this app
// (the Registry the Glossary hands over, the verdict Drift produces) and are
// deliberately not clickable. All colours come from theme variables.
//
// The stages are drawn in a single row because they genuinely are a sequence —
// the numbering in the stepper means the same thing. Report hangs off the row
// on a dotted edge: it reads every stage but is not a step you pass through.

const STAGES = [
  { id: 'load', label: 'Load', x: 6, w: 54,
    hint: 'Open the Registry the Glossary wrote — the contract everything downstream reads.' },
  { id: 'author', label: 'Author', x: 78, w: 64,
    hint: 'Turn each governed row into an import-ready pattern or dictionary. Offline and deterministic.' },
  { id: 'reconcile', label: 'Reconcile', x: 160, w: 84,
    hint: 'Look every term up in live PDC and bind by id instead of by name. Needs a session.' },
  { id: 'deploy', label: 'Deploy', x: 262, w: 64,
    hint: 'Import the authored set into PDC, verify each method landed, re-stamp the term ids.' },
  { id: 'drift', label: 'Drift', x: 344, w: 54,
    hint: 'Read the catalog back and compare it against the contract, method by method.' },
]

function Node({ id, label, hint, x, y, w, h, small, onNavigate }) {
  const activate = () => onNavigate?.(id)
  return (
    <g
      className={small ? 'wf-node wf-node-sm' : 'wf-node'}
      role="link"
      tabIndex={0}
      aria-label={`Go to ${label}`}
      onClick={activate}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          activate()
        }
      }}
    >
      {hint && <title>{hint}</title>}
      <rect x={x} y={y} width={w} height={h} rx="8" />
      <text x={x + w / 2} y={y + h / 2 + 1} textAnchor="middle" dominantBaseline="middle">
        {label}
      </text>
    </g>
  )
}

const Arrow = ({ d, dotted }) => (
  <path d={d} className={dotted ? 'wf-arrow wf-dotted' : 'wf-arrow'} markerEnd="url(#wf-arrowhead)" />
)

export default function WorkflowDiagram({ onNavigate }) {
  return (
    <div className="wf-wrap">
      <svg
        className="wf"
        viewBox="0 0 700 110"
        aria-label="Workflow: Load the Classification Registry the Glossary Generator wrote, then
          Author patterns and dictionaries from it, then Reconcile to bind every term by id
          against live PDC, then Deploy the set into PDC, then Drift to compare what is deployed
          against what the Registry governs. Report reads every stage and is not itself a step."
      >
        <defs>
          <marker id="wf-arrowhead" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse"
                  orient="auto-start-reverse">
            <path className="wf-head" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
          </marker>
        </defs>

        {/* the sequence */}
        <Arrow d="M64 28 H74" />
        <Arrow d="M146 28 H156" />
        <Arrow d="M248 28 H258" />
        <Arrow d="M330 28 H340" />
        {STAGES.map((n) => (
          <Node key={n.id} {...n} y={10} h={36} onNavigate={onNavigate} />
        ))}

        {/* what arrives: the contract, written by the other app */}
        <Arrow d="M33 70 V50" />
        <g className="wf-out">
          <rect x="6" y="70" width="190" height="26" rx="8" />
          <text x="101" y="84" textAnchor="middle" dominantBaseline="middle">
            Registry ← Glossary Generator
          </text>
        </g>

        {/* what leaves: a verdict per method, which is the point of the pipeline */}
        <Arrow d="M402 28 H426" />
        <g className="wf-out">
          <rect x="430" y="15" width="262" height="26" rx="8" />
          <text x="561" y="29" textAnchor="middle" dominantBaseline="middle">
            clean · drifted · missing · orphaned
          </text>
        </g>

        {/* Report reads the lot — dotted, because it is not a step in the chain */}
        <Arrow dotted d="M371 46 V82 H424" />
        <Node id="report" label="Report" x={430} y={70} w={72} h={24} small
              hint="One account of the whole pipeline — contract, authored set, live catalog. Exportable."
              onNavigate={onNavigate} />
      </svg>
    </div>
  )
}
