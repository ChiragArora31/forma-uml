import { ArrowRight, Loader2, Workflow } from 'lucide-react';
import type { Session } from './types';
export default function WelcomeCanvas({
  session,
  busy,
  onStart,
}: {
  session: Session;
  busy: boolean;
  onStart: () => void;
}) {
  return (
    <div className="welcome-canvas">
      <div className="welcome-topline">
        <span className="eyebrow">MAKE THE SYSTEM MAKE SENSE</span>
        <span className="sheet-number">FIG. 001</span>
      </div>
      <div className="welcome-copy">
        <span className="studio-tag">
          <span /> A SPACE TO THINK IN SYSTEMS
        </span>
        <h1>
          From a brief
          <br />
          to a <em>blueprint.</em>
        </h1>
        <p>
          Explore the architecture. Trace the interactions.
          <br />
          Build on a design you can actually understand.
        </p>
      </div>
      <div className="blueprint-sketch" aria-hidden="true">
        <svg viewBox="0 0 640 260">
          <defs>
            <marker
              id="arrow"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="5"
              markerHeight="5"
              orient="auto-start-reverse"
            >
              <path d="M0 0L10 5L0 10" fill="none" stroke="#81998b" />
            </marker>
          </defs>
          <g fill="none" stroke="#93a599" strokeWidth="1.3">
            <path d="M145 125H260M390 125H500M325 160V215H145V160" markerEnd="url(#arrow)" />
            <rect x="25" y="85" width="120" height="75" rx="3" />
            <rect x="260" y="85" width="130" height="75" rx="3" />
            <rect x="500" y="85" width="120" height="75" rx="3" />
            <rect x="88" y="42" width="15" height="15" rx="2" transform="rotate(45 95 50)" />
            <path d="M95 61V85" strokeDasharray="3 4" />
            <path d="M563 160v35" strokeDasharray="3 4" />
            <circle cx="562" cy="203" r="8" />
          </g>
          <g fontFamily="monospace" fill="#526b5b" fontSize="12" textAnchor="middle">
            <text x="85" y="117">
              The brief
            </text>
            <text x="85" y="137" fontSize="9" fill="#92a094">
              your intent
            </text>
            <text x="325" y="117">
              System model
            </text>
            <text x="325" y="137" fontSize="9" fill="#92a094">
              shared understanding
            </text>
            <text x="560" y="117">
              UML views
            </text>
            <text x="560" y="137" fontSize="9" fill="#92a094">
              the full picture
            </text>
            <text x="219" y="234" fontSize="9" fill="#92a094">
              refine together
            </text>
          </g>
        </svg>
        <span className="sketch-annotation">a little structure. a lot of clarity.</span>
      </div>
      <div className="welcome-bottom">
        <div>
          <span className="number-label">01 / DESCRIBE</span>
          <strong>Your idea, in plain language.</strong>
        </div>
        <div>
          <span className="number-label">02 / EXPLORE</span>
          <strong>14 perspectives on one system.</strong>
        </div>
        <div>
          <span className="number-label">03 / REFINE</span>
          <strong>Every iteration, preserved.</strong>
        </div>
      </div>
      <button className="welcome-cta" onClick={onStart} disabled={busy}>
        {busy ? <Loader2 size={16} className="spin" /> : <Workflow size={17} />}Open the SEBI case
        study
        <ArrowRight size={16} />
      </button>
      <p className="sample-disclosure">
        {session.mode === 'sample'
          ? 'Curated sample · No API key needed · Real UML rendering'
          : 'Generate the assignment brief with your configured model'}
      </p>
    </div>
  );
}
