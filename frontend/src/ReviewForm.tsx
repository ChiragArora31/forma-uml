import { useRef, useState } from 'react';
import { Check, Loader2, ShieldCheck, Star } from 'lucide-react';
import { api } from './api';
import type { CatalogEntry, DiagramKind, Feedback, Revision } from './types';

interface Props {
  revision: Revision;
  catalog: CatalogEntry[];
  onBusy: (busy: boolean) => void;
  onReviewed: (review: Feedback) => void;
}
export default function ReviewForm({ revision, catalog, onBusy, onReviewed }: Props) {
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');
  const [scope, setScope] = useState<'all' | DiagramKind>('all');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const pending = useRef<{ key: string; requestId: string } | null>(null);
  const label = (kind: DiagramKind) => catalog.find((entry) => entry.id === kind)?.label ?? kind;
  async function saveReview() {
    if (!rating || busy) return;
    setBusy(true);
    onBusy(true);
    setError('');
    const key = JSON.stringify({ revision: revision.id, rating, comment, scope });
    if (pending.current?.key !== key) pending.current = { key, requestId: crypto.randomUUID() };
    try {
      const review = await api<Feedback>('/feedback', {
        method: 'POST',
        body: JSON.stringify({
          revision_id: revision.id,
          rating,
          comment,
          diagram_type: scope === 'all' ? null : scope,
          request_id: pending.current.requestId,
        }),
      });
      pending.current = null;
      onReviewed(review);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <>
      <span className="eyebrow">YOUR PERSPECTIVE MATTERS</span>
      <h2 id="modal-title">Review the blueprint.</h2>
      <p>
        Feedback is tied to revision {revision.number}, saved with its design context, and queued
        for the ART trainer.
      </p>
      <label className="form-label">
        Review scope
        <select value={scope} onChange={(e) => setScope(e.target.value as 'all' | DiagramKind)}>
          <option value="all">Entire design</option>
          {revision.diagrams.map((d) => (
            <option key={d.type} value={d.type}>
              {label(d.type)} diagram
            </option>
          ))}
        </select>
      </label>
      <fieldset className="rating-field">
        <legend>How useful is this design?</legend>
        <div className="stars">
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              aria-label={`Rate ${n} out of 5`}
              aria-pressed={rating === n}
              onClick={() => setRating(n)}
            >
              <Star size={30} fill={n <= rating ? 'currentColor' : 'none'} />
            </button>
          ))}
        </div>
        <span>
          {
            [
              'Choose a rating',
              'Needs a rethink',
              'Needs substantial work',
              'A useful starting point',
              'Clear and well considered',
              'Ready to build on',
            ][rating]
          }
        </span>
      </fieldset>
      <label className="form-label">
        What worked? What needs to change?
        <textarea
          placeholder="For example: keep the evidence store, but move extraction into an async worker…"
          maxLength={4000}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </label>
      <p className="training-note">
        <ShieldCheck size={14} />
        Saving feedback queues a training scenario. Model weights change only when the separate ART
        training job runs.
      </p>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
      <div className="modal-footer">
        <span>
          {revision.mode === 'sample'
            ? 'Sample reviews are excluded from RL training.'
            : 'Your review also guides future live revisions.'}
        </span>
        <button className="primary" disabled={!rating || busy} onClick={saveReview}>
          {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />}Save review
        </button>
      </div>
    </>
  );
}
