import { useState } from 'react';
import { Archive, Check, Loader2, RotateCcw } from 'lucide-react';
import { api } from './api';
import type { Conversation } from './types';

export default function WorkspaceSettings({
  conversation,
  onBusy,
  onSaved,
}: {
  conversation: Conversation;
  onBusy: (busy: boolean) => void;
  onSaved: (c: Conversation, archived: boolean) => void;
}) {
  const [title, setTitle] = useState(conversation.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function save(changes: { title?: string; archived?: boolean }) {
    if (busy) return;
    setBusy(true);
    onBusy(true);
    setError('');
    try {
      const c = await api<Conversation>(`/conversations/${conversation.id}`, {
        method: 'PATCH',
        body: JSON.stringify(changes),
      });
      onSaved(c, changes.archived === true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      onBusy(false);
    }
  }
  return (
    <>
      <span className="eyebrow">YOUR WORKSPACE</span>
      <h2 id="modal-title">Give this design a home.</h2>
      <p>Organize your workspace while preserving every blueprint, review, and revision.</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save({ title: title.trim() });
        }}
      >
        <label className="form-label">
          Design name
          <input
            autoFocus
            value={title}
            maxLength={100}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
          />
        </label>
        <div className="modal-footer">
          <span>The original blueprint title stays in its history.</span>
          <button
            className="primary"
            disabled={busy || !title.trim() || title.trim() === conversation.title}
          >
            {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />}Save name
          </button>
        </div>
      </form>
      <div className="archive-setting">
        <div>
          <strong>
            {conversation.archived
              ? 'Bring it back to your workspace'
              : 'Make room for your next idea'}
          </strong>
          <p>
            {conversation.archived
              ? 'Restore the design to continue its conversation.'
              : 'Archiving keeps all your work. You can restore it at any time.'}
          </p>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void save({ archived: !conversation.archived })}
        >
          {conversation.archived ? <RotateCcw size={15} /> : <Archive size={15} />}
          {conversation.archived ? 'Restore design' : 'Archive design'}
        </button>
      </div>
      {error && (
        <p className="inline-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
