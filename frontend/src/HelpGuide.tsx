import type { Session } from './types';
export default function HelpGuide({ session }: { session: Session }) {
  return (
    <>
      <span className="eyebrow">A LITTLE GUIDANCE</span>
      <h2 id="modal-title">Design with intention.</h2>
      <div className="help-step">
        <span>01</span>
        <div>
          <h3>Describe your system</h3>
          <p>
            Include the goal, actors, constraints, and important data. Choose the views that answer
            your questions.
          </p>
        </div>
      </div>
      <div className="help-step">
        <span>02</span>
        <div>
          <h3>Explore a consistent blueprint</h3>
          <p>
            One typed system model produces all selected diagrams. Every saved diagram passes real
            PlantUML syntax validation. Review the assumptions in Design notes.
          </p>
        </div>
      </div>
      <div className="help-step">
        <span>03</span>
        <div>
          <h3>Iterate without losing your thinking</h3>
          <p>
            Send an updated brief or a specific change. Revisions are saved in your workspace; use
            the version picker to revisit any saved design.
          </p>
        </div>
      </div>
      <div className="help-step">
        <span>04</span>
        <div>
          <h3>Review, then take it with you</h3>
          <p>
            Ratings and comments are saved against the exact revision for ART training. Export
            includes SVG, editable PlantUML, the system model, a design review brief, and your
            feedback.
          </p>
        </div>
      </div>
      <div className="help-mode">
        <strong>
          {session.mode === 'sample' ? 'You’re in sample mode' : 'You’re in live mode'}
        </strong>
        <p>
          {session.mode === 'sample'
            ? 'The SEBI architecture and two suggested updates are curated fixtures. Use the suggested case-study refinements. Live AI accepts your own systems when available.'
            : `Your configured model is ${session.model}. API keys stay on the server.`}
        </p>
        <p>
          Your saved designs are private to this browser. Draft briefs and source previews are saved
          as you work. Keep the browser cookie to retain workspace access, and export designs you
          want to share.
        </p>
        {session.mode === 'live' && (
          <p>
            Your brief is sent to the configured model for generation. This free Gemini demo follows{' '}
            <a
              className="text-link"
              href="https://ai.google.dev/gemini-api/terms"
              target="_blank"
              rel="noreferrer"
            >
              Google’s free-service data terms
            </a>
            ; use non-sensitive example designs.
          </p>
        )}
      </div>
    </>
  );
}
