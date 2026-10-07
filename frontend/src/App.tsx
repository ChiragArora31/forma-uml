import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ArrowDownToLine,
  ArrowUp,
  ArrowUpRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Code2,
  Copy,
  FileCode2,
  GitBranch,
  History,
  Layers,
  Loader2,
  Maximize2,
  MessageSquare,
  Minimize2,
  Plus,
  Search,
  ShieldCheck,
  Square,
  ThumbsUp,
  Workflow,
  X,
} from 'lucide-react';
import { api, download, generate } from './api';
import type { GeneratePayload } from './api';
import type {
  Conversation,
  ConversationSummary,
  DiagramKind,
  Feedback,
  Revision,
  Session,
} from './types';
import DiagramCanvas from './DiagramCanvas';
import WelcomeCanvas from './WelcomeCanvas';
import HelpGuide from './HelpGuide';
import DiagramPicker from './DiagramPicker';
import ReviewForm from './ReviewForm';

type View = 'diagram' | 'source' | 'notes' | 'compare';
type Modal = 'diagrams' | 'review' | 'help' | null;
const DEFAULT_TYPES: DiagramKind[] = ['sequence', 'component'];

function Mark({ small = false }: { small?: boolean }) {
  return (
    <span className={`brand-mark ${small ? 'small' : ''}`} aria-hidden="true">
      <span />
      <span />
      <span />
    </span>
  );
}
function formatTime(value: string) {
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}
function revisionChanges(previous: Revision, current: Revision) {
  const before = new Map(previous.architecture.components.map((c) => [c.id, c]));
  const after = new Map(current.architecture.components.map((c) => [c.id, c]));
  const entries = [...after.values()]
    .filter((c) => !before.has(c.id))
    .map((c) => ({ status: 'Added', name: c.name, detail: c.responsibility }));
  for (const c of before.values())
    if (!after.has(c.id))
      entries.push({ status: 'Removed', name: c.name, detail: c.responsibility });
  for (const c of after.values())
    if (before.has(c.id) && JSON.stringify(c) !== JSON.stringify(before.get(c.id)))
      entries.push({ status: 'Changed', name: c.name, detail: c.responsibility });
  for (const r of current.architecture.requirements)
    if (!previous.architecture.requirements.includes(r))
      entries.push({ status: 'Added', name: 'Requirement', detail: r });
  for (const r of previous.architecture.requirements)
    if (!current.architecture.requirements.includes(r))
      entries.push({ status: 'Removed', name: 'Requirement', detail: r });
  const connectionKey = (c: Revision['architecture']['connections'][number]) => JSON.stringify(c);
  for (const c of current.architecture.connections)
    if (!previous.architecture.connections.some((p) => connectionKey(p) === connectionKey(c)))
      entries.push({
        status: 'Added',
        name: 'Connection',
        detail: `${c.source} → ${c.target}: ${c.label}`,
      });
  for (const c of previous.architecture.connections)
    if (!current.architecture.connections.some((p) => connectionKey(p) === connectionKey(c)))
      entries.push({
        status: 'Removed',
        name: 'Connection',
        detail: `${c.source} → ${c.target}: ${c.label}`,
      });
  return entries;
}

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [revisionIndex, setRevisionIndex] = useState(-1);
  const [types, setTypes] = useState<DiagramKind[]>(DEFAULT_TYPES);
  const [kind, setKind] = useState<DiagramKind>('component');
  const [prompt, setPrompt] = useState('');
  const [view, setView] = useState<View>('diagram');
  const [modal, setModal] = useState<Modal>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');
  const [error, setError] = useState('');
  const [toast, setToast] = useState('');
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [source, setSource] = useState('');
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviews, setReviews] = useState<Feedback[]>([]);
  const [bootError, setBootError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const pending = useRef<{ payload: GeneratePayload; prompt: string } | null>(null);
  const feed = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const modalRef = useRef<HTMLDialogElement>(null);
  const revision = conversation?.revisions[revisionIndex] ?? null;
  const diagram = revision?.diagrams.find((d) => d.type === kind) ?? revision?.diagrams[0];
  const label = (k: DiagramKind) => session?.diagram_types.find((d) => d.id === k)?.label ?? k;

  const refresh = useCallback(async () => {
    setConversations(await api<ConversationSummary[]>('/conversations'));
  }, []);
  useEffect(() => {
    let alive = true;
    api<Session>('/session')
      .then(async (s) => {
        if (!alive) return;
        setSession(s);
        await refresh();
      })
      .catch((e) => {
        if (alive) setBootError(e.message);
      });
    return () => {
      alive = false;
      controller.current?.abort();
    };
  }, [refresh]);
  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(''), 4000);
      return () => clearTimeout(t);
    }
  }, [toast]);
  useEffect(() => {
    feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: 'smooth' });
  }, [conversation, busy, phase]);
  useEffect(() => {
    setSource(diagram?.source ?? '');
    setSourcePreview(null);
    setSourceError('');
  }, [diagram]);
  useEffect(() => {
    let alive = true;
    setReviews([]);
    if (revision)
      api<Feedback[]>(`/revisions/${revision.id}/feedback`)
        .then((r) => {
          if (alive) setReviews(r);
        })
        .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [revision]);
  useEffect(() => {
    const dialog = modalRef.current;
    if (modal && dialog && !dialog.open) dialog.showModal();
    else if (!modal && dialog?.open) dialog.close();
  }, [modal]);
  useEffect(() => {
    function escape(e: KeyboardEvent) {
      if (e.key === 'Escape') setExpanded(false);
    }
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, []);

  function reset() {
    if (busy) return;
    setConversation(null);
    setRevisionIndex(-1);
    setPrompt('');
    setError('');
    setView('diagram');
    setTypes(DEFAULT_TYPES);
    setKind('component');
    pending.current = null;
    textarea.current?.focus();
  }
  async function openConversation(id: string) {
    if (busy) return;
    try {
      const c = await api<Conversation>(`/conversations/${id}`);
      setConversation(c);
      setRevisionIndex(c.revisions.length - 1);
      setTypes(c.revisions.at(-1)!.diagrams.map((d) => d.type));
      setKind(
        c.revisions.at(-1)!.diagrams.some((d) => d.type === 'component')
          ? 'component'
          : c.revisions.at(-1)!.diagrams[0].type,
      );
      setView('diagram');
      setError('');
      setPrompt('');
      pending.current = null;
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function send(override?: string, overrideTypes?: DiagramKind[]) {
    const input = (override ?? prompt).trim();
    const selectedTypes = overrideTypes ?? types;
    if (!session || busy || input.length < 10 || !selectedTypes.length) return;
    const latest = conversation?.revisions.at(-1);
    const draft: GeneratePayload = {
      prompt: input,
      diagram_types: selectedTypes,
      ...(conversation ? { conversation_id: conversation.id, base_revision: latest!.number } : {}),
      request_id: crypto.randomUUID(),
    };
    // A retry of the exact same action reuses its ID, including after a network failure.
    const old = pending.current?.payload;
    const same =
      old &&
      old.prompt === draft.prompt &&
      old.conversation_id === draft.conversation_id &&
      old.base_revision === draft.base_revision &&
      old.diagram_types.join() === draft.diagram_types.join();
    const payload = same ? old : draft;
    pending.current = { payload, prompt: input };
    if (override) setPrompt(input);
    controller.current = new AbortController();
    setBusy(true);
    setError('');
    setPhase('Preparing your design');
    try {
      const result = await generate(payload, controller.current.signal, setPhase);
      const c = await api<Conversation>(`/conversations/${result.conversation_id}`);
      setConversation(c);
      setRevisionIndex(c.revisions.findIndex((r) => r.id === result.id));
      setPrompt('');
      setTypes(selectedTypes);
      setKind(result.diagrams.some((d) => d.type === kind) ? kind : result.diagrams[0].type);
      setView('diagram');
      pending.current = null;
      await refresh();
    } catch (e) {
      if ((e as Error).name === 'AbortError')
        setToast(
          'Generation stopped. Reload history to check whether a revision was already saved.',
        );
      else setError((e as Error).message);
    } finally {
      setBusy(false);
      setPhase('');
      controller.current = null;
    }
  }
  async function validateSource() {
    setSourceBusy(true);
    setSourceError('');
    try {
      const r = await api<{ svg: string }>('/render', {
        method: 'POST',
        body: JSON.stringify({ source }),
      });
      setSourcePreview(r.svg);
      setToast('Syntax checked. This is a local preview; the saved revision is unchanged.');
    } catch (e) {
      setSourceError((e as Error).message);
      setSourcePreview(null);
    } finally {
      setSourceBusy(false);
    }
  }
  async function copySource() {
    try {
      await navigator.clipboard.writeText(source);
      setToast('PlantUML source copied');
    } catch {
      setToast('Clipboard unavailable. Use the source download instead.');
    }
  }
  function openReview() {
    setModal('review');
  }

  if (bootError)
    return (
      <div className="boot-error">
        <Mark />
        <h1>Let’s reconnect.</h1>
        <p>{bootError}</p>
        <button className="primary" onClick={() => location.reload()}>
          Retry connection
        </button>
      </div>
    );
  if (!session)
    return (
      <div className="boot-error">
        <Mark />
        <Loader2 className="spin" />
        <p>Opening your workspace…</p>
      </div>
    );
  const previous =
    conversation && revisionIndex > 0 ? conversation.revisions[revisionIndex - 1] : null;
  const isHistoric = conversation && revisionIndex < conversation.revisions.length - 1;

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            reset();
          }}
        >
          <Mark />
          <span>
            forma<span className="brand-period">.</span>
          </span>
        </a>
        <div className="workspace-label">SOFTWARE DESIGN STUDIO</div>
        <button className="new-design" aria-label="New design" onClick={reset} disabled={busy}>
          <Plus size={17} /> New design <span>↗</span>
        </button>
        <div className="sidebar-section-title">
          <span>YOUR WORKSPACE</span>
          <span>{conversations.length.toString().padStart(2, '0')}</span>
        </div>
        <label className="search-field">
          <Search size={14} />
          <input
            aria-label="Search designs"
            placeholder="Find a design…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <nav className="design-list" aria-label="Saved designs">
          {conversations
            .filter((c) => c.title.toLowerCase().includes(query.toLowerCase()))
            .map((c) => (
              <button
                key={c.id}
                className={`design-item ${conversation?.id === c.id ? 'active' : ''}`}
                onClick={() => openConversation(c.id)}
                disabled={busy}
              >
                <Workflow size={16} />
                <span>
                  <strong>{c.title}</strong>
                  <small>
                    {c.latest} revision{c.latest === 1 ? '' : 's'}
                  </small>
                </span>
              </button>
            ))}
          {!conversations.length && (
            <p className="empty-history">
              Your designs will live here.
              <br />
              Start with a brief below.
            </p>
          )}
        </nav>
        <div className="sidebar-bottom">
          <button className="guide-link" onClick={() => setModal('help')}>
            <BookOpen size={16} /> A little guidance <ArrowUpRight size={14} />
          </button>
          <div className="local-identity">
            <span className="identity-icon">
              <Layers size={16} />
            </span>
            <div>
              <strong>Your local workspace</strong>
              <small>Saved privately in this browser session</small>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>{revision?.architecture.title ?? 'Untitled design'}</strong>
          </div>
          <div className="top-actions">
            <span className="mode-indicator">
              <i />
              {session.mode === 'sample' ? 'Sample mode' : 'Live generation'}
            </span>
            <button
              className="icon-button"
              aria-label="How Forma works"
              onClick={() => setModal('help')}
            >
              <CircleHelp size={18} />
            </button>
          </div>
        </header>
        <div className="workspace">
          <section className="conversation-panel" aria-label="Design conversation">
            <div className="panel-heading">
              <div>
                <MessageSquare size={16} />
                <h2>Design conversation</h2>
              </div>
              <span className="tiny-label">
                {conversation ? `${conversation.revisions.length} ITERATIONS` : 'LET’S BEGIN'}
              </span>
            </div>
            <div className="conversation-feed" ref={feed}>
              <div className="intro-message">
                <div className="speaker">
                  <Mark small />
                  <strong>Forma</strong>
                  <span>YOUR DESIGN PARTNER</span>
                </div>
                <p>Good software starts with a clear picture.</p>
                <p className="muted">
                  Describe what you’re building. We’ll turn the brief into a connected set of UML
                  diagrams, then refine the design together.
                </p>
              </div>
              {!conversation && !busy && (
                <div className="sample-brief">
                  <div className="eyebrow">
                    <span className="sample-dot" /> A GOOD PLACE TO START
                  </div>
                  <h3>
                    Regulatory compliance,
                    <br />
                    mapped from end to end.
                  </h3>
                  <p>SEBI circulars → clause extraction → control gaps → organizational impact.</p>
                  <button
                    onClick={() => {
                      setPrompt(session.sample_prompt);
                      textarea.current?.focus();
                    }}
                  >
                    Use the assignment brief <ArrowUpRight size={15} />
                  </button>
                </div>
              )}
              {conversation?.revisions.map((r, i) => (
                <div
                  className={`conversation-turn ${i > revisionIndex ? 'future-turn' : ''}`}
                  key={r.id}
                >
                  <div className="user-message">
                    <div className="speaker">
                      <span className="user-dot">Y</span>
                      <strong>You</strong>
                      <time>{formatTime(r.created_at)}</time>
                    </div>
                    <p>{r.prompt}</p>
                  </div>
                  <div className="assistant-message">
                    <div className="speaker">
                      <Mark small />
                      <strong>Forma</strong>
                      <span className="revision-tag">v{r.number}</span>
                    </div>
                    <p>
                      {i === 0
                        ? 'Here’s a first blueprint for your system.'
                        : 'Your updated blueprint is ready.'}
                    </p>
                    <p className="muted">{r.architecture.summary}</p>
                    <button
                      className={`revision-card ${revision?.id === r.id ? 'selected' : ''}`}
                      onClick={() => {
                        setRevisionIndex(i);
                        if (!r.diagrams.some((d) => d.type === kind)) setKind(r.diagrams[0].type);
                        setView('diagram');
                      }}
                    >
                      <span className="revision-card-icon">
                        <Layers size={20} />
                      </span>
                      <span>
                        <strong>{r.diagrams.length} verified UML views</strong>
                        <small>
                          Revision {r.number} · {r.architecture.components.length} components
                        </small>
                      </span>
                      <ArrowUpRight size={16} />
                    </button>
                  </div>
                </div>
              ))}
              {busy && (
                <div className="progress-card" role="status">
                  <Loader2 size={17} className="spin" />
                  <div>
                    <strong>{phase}</strong>
                    <small>
                      {session.mode === 'sample'
                        ? 'Rendering the curated case study with PlantUML'
                        : 'One shared design. Consistent views.'}
                    </small>
                  </div>
                  <button aria-label="Stop generation" onClick={() => controller.current?.abort()}>
                    <Square size={12} />
                  </button>
                </div>
              )}
              {error && (
                <div className="error-message" role="alert">
                  <strong>We couldn’t finish this design.</strong>
                  <p>{error}</p>
                  {conversation && (
                    <button onClick={() => openConversation(conversation.id)}>
                      Reload saved revisions
                    </button>
                  )}
                </div>
              )}
              {revision && !busy && (
                <div className="next-steps">
                  <span className="tiny-label">KEEP THE DESIGN MOVING</span>
                  {session.mode === 'sample' ? (
                    session.sample_updates.map((p, i) => (
                      <button
                        key={p}
                        onClick={() => {
                          setPrompt(p);
                          textarea.current?.focus();
                        }}
                      >
                        <GitBranch size={13} />
                        {i === 0
                          ? 'Add a queue, retries & failure recovery'
                          : 'Require officer approval before publication'}
                        <Plus size={13} />
                      </button>
                    ))
                  ) : (
                    <p className="muted">
                      Add a constraint, change a boundary, or describe the next iteration.
                    </p>
                  )}
                </div>
              )}
            </div>
            <div className="composer-area">
              {isHistoric && (
                <p className="historic-note">
                  <History size={12} /> Viewing v{revision!.number}. New requests update v
                  {conversation!.latest}.
                </p>
              )}
              <div className="selected-types">
                <span>VIEWS</span>
                {types.slice(0, 3).map((t) => (
                  <button key={t} onClick={() => setModal('diagrams')}>
                    {label(t)}
                  </button>
                ))}
                {types.length > 3 && <span>+{types.length - 3}</span>}
                <button
                  className="type-add"
                  aria-label="Choose UML diagram types"
                  onClick={() => setModal('diagrams')}
                >
                  <Plus size={13} />
                </button>
              </div>
              <div className="composer">
                <textarea
                  ref={textarea}
                  aria-label="Describe your software design"
                  placeholder={
                    conversation
                      ? 'What would you like to change?'
                      : 'Describe the system you have in mind…'
                  }
                  value={prompt}
                  maxLength={12000}
                  onChange={(e) => setPrompt(e.target.value)}
                  disabled={busy}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                />
                <div className="composer-footer">
                  <span>
                    {prompt.length
                      ? `${prompt.length.toLocaleString()} / 12,000`
                      : 'A clear brief goes a long way.'}
                  </span>
                  <button
                    className="send-button"
                    aria-label="Send design request"
                    disabled={busy || prompt.trim().length < 10 || !types.length}
                    onClick={() => void send()}
                  >
                    {busy ? <Loader2 size={17} className="spin" /> : <ArrowUp size={18} />}
                  </button>
                </div>
              </div>
              <div className="composer-hint">
                <span>
                  ↵ Send <span className="hint-separator">·</span> Shift + ↵ New line
                </span>
                <ShieldCheck size={12} />
              </div>
            </div>
          </section>

          <section
            className={`artifact-panel ${expanded ? 'expanded' : ''}`}
            aria-label="Design workspace"
          >
            {!revision ? (
              <WelcomeCanvas
                session={session}
                busy={busy}
                onStart={() => void send(session.sample_prompt)}
              />
            ) : (
              <>
                <div className="artifact-heading">
                  <div>
                    <span className="eyebrow">THE BLUEPRINT</span>
                    <h1>{revision.architecture.title}</h1>
                  </div>
                  <label className="version-select">
                    <GitBranch size={14} />
                    <select
                      aria-label="Select revision"
                      value={revisionIndex}
                      onChange={(e) => setRevisionIndex(Number(e.target.value))}
                    >
                      {conversation!.revisions.map((r, i) => (
                        <option key={r.id} value={i}>
                          v{r.number}
                          {i === conversation!.revisions.length - 1 ? ' · Latest' : ''}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={12} />
                  </label>
                </div>
                <div className="diagram-tabs-row">
                  <div className="diagram-tabs" role="tablist" aria-label="Generated UML diagrams">
                    {revision.diagrams.map((d) => (
                      <button
                        id={`tab-${d.type}`}
                        role="tab"
                        aria-controls="uml-view-panel"
                        tabIndex={diagram?.type === d.type ? 0 : -1}
                        onKeyDown={(e) => {
                          const index = revision.diagrams.findIndex((item) => item.type === d.type);
                          const next =
                            e.key === 'ArrowRight'
                              ? (index + 1) % revision.diagrams.length
                              : e.key === 'ArrowLeft'
                                ? (index - 1 + revision.diagrams.length) % revision.diagrams.length
                                : e.key === 'Home'
                                  ? 0
                                  : e.key === 'End'
                                    ? revision.diagrams.length - 1
                                    : -1;
                          if (next >= 0) {
                            e.preventDefault();
                            const nextKind = revision.diagrams[next].type;
                            setKind(nextKind);
                            setView('diagram');
                            document.getElementById(`tab-${nextKind}`)?.focus();
                          }
                        }}
                        aria-selected={diagram?.type === d.type}
                        className={diagram?.type === d.type ? 'active' : ''}
                        key={d.type}
                        onClick={() => {
                          setKind(d.type);
                          setView('diagram');
                        }}
                      >
                        {d.type === 'sequence' ? <Workflow size={14} /> : <Layers size={14} />}
                        {label(d.type)}
                      </button>
                    ))}
                  </div>
                  <button
                    className="tab-add"
                    aria-label="Change diagrams for next iteration"
                    onClick={() => setModal('diagrams')}
                  >
                    <Plus size={15} />
                  </button>
                </div>
                <div
                  className="canvas-frame"
                  id="uml-view-panel"
                  role="tabpanel"
                  aria-labelledby={`tab-${diagram?.type}`}
                  tabIndex={0}
                >
                  <div className="canvas-toolbar">
                    <div className="view-switch">
                      <button
                        className={view === 'diagram' ? 'active' : ''}
                        onClick={() => setView('diagram')}
                      >
                        <Workflow size={13} />
                        Diagram
                      </button>
                      <button
                        className={view === 'source' ? 'active' : ''}
                        onClick={() => setView('source')}
                      >
                        <Code2 size={13} />
                        Source
                      </button>
                      <button
                        className={view === 'notes' ? 'active' : ''}
                        onClick={() => setView('notes')}
                      >
                        Design notes
                      </button>
                      {previous && (
                        <button
                          className={view === 'compare' ? 'active' : ''}
                          onClick={() => setView('compare')}
                        >
                          <GitBranch size={13} />
                          Changes
                        </button>
                      )}
                    </div>
                    <div className="canvas-actions">
                      <span className="validated-pill">
                        <Check size={11} />
                        Syntax verified
                      </span>
                      <button
                        className="icon-button"
                        aria-label={expanded ? 'Exit full screen' : 'Expand canvas'}
                        onClick={() => setExpanded((v) => !v)}
                      >
                        {expanded ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
                      </button>
                    </div>
                  </div>
                  {view === 'diagram' && diagram && (
                    <DiagramCanvas svg={diagram.svg} label={label(diagram.type)} />
                  )}
                  {view === 'source' && (
                    <div className="source-view">
                      <div className="source-caption">
                        <span>
                          <FileCode2 size={14} />
                          {diagram?.type}.puml
                        </span>
                        <div className="source-downloads">
                          <button
                            onClick={() => download(source, `${diagram?.type}.puml`, 'text/plain')}
                          >
                            <ArrowDownToLine size={13} /> .puml
                          </button>
                          <button
                            onClick={() =>
                              diagram &&
                              download(diagram.svg, `${diagram.type}.svg`, 'image/svg+xml')
                            }
                          >
                            <ArrowDownToLine size={13} /> .svg
                          </button>
                          <button onClick={copySource}>
                            <Copy size={13} /> Copy
                          </button>
                        </div>
                      </div>
                      <textarea
                        aria-label="PlantUML source editor"
                        spellCheck={false}
                        value={source}
                        onChange={(e) => {
                          setSource(e.target.value);
                          setSourcePreview(null);
                        }}
                      />
                      <div className="source-actions">
                        <p>Edits are a local preview. Saved revisions stay intact.</p>
                        <button
                          className="primary compact"
                          onClick={validateSource}
                          disabled={sourceBusy}
                        >
                          {sourceBusy ? (
                            <Loader2 size={14} className="spin" />
                          ) : (
                            <CheckCheck size={14} />
                          )}
                          Check & preview
                        </button>
                      </div>
                      {sourceError && (
                        <p className="inline-error" role="alert">
                          {sourceError}
                        </p>
                      )}
                      {sourcePreview && (
                        <div className="source-preview">
                          <DiagramCanvas svg={sourcePreview} label="Edited preview" />
                        </div>
                      )}
                    </div>
                  )}
                  {view === 'notes' && (
                    <div className="design-notes">
                      <span className="eyebrow">DESIGN RATIONALE</span>
                      <h2>One model. Many perspectives.</h2>
                      <p>{revision.architecture.summary}</p>
                      <h3>Requirements covered</h3>
                      <ol>
                        {revision.architecture.requirements.map((r) => (
                          <li key={r}>{r}</li>
                        ))}
                      </ol>
                      <h3>Assumptions to validate</h3>
                      <ul>
                        {revision.architecture.assumptions.map((a) => (
                          <li key={a}>{a}</li>
                        ))}
                      </ul>
                      <h3>System boundaries</h3>
                      <div className="boundary-list">
                        {revision.architecture.components.map((c) => (
                          <div key={c.id}>
                            <strong>{c.name}</strong>
                            <span>{c.responsibility}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {view === 'compare' && previous && (
                    <div className="changes-view">
                      <span className="eyebrow">ITERATION HISTORY</span>
                      <h2>What changed in v{revision.number}?</h2>
                      <p>
                        Compared with v{previous.number}. Components, requirements, and connections.
                      </p>
                      {revisionChanges(previous, revision).length ? (
                        revisionChanges(previous, revision).map((change, i) => (
                          <div className="change-row" key={i}>
                            <span className={`change-status ${change.status.toLowerCase()}`}>
                              {change.status}
                            </span>
                            <div>
                              <strong>{change.name}</strong>
                              <p>{change.detail}</p>
                            </div>
                          </div>
                        ))
                      ) : (
                        <p>
                          No changes to components, requirements, or connections. Other design
                          details may have changed; inspect the source and design notes.
                        </p>
                      )}
                    </div>
                  )}
                  <div className="canvas-status">
                    <span>
                      <span className="status-dot" />
                      PlantUML · {revision.mode === 'sample' ? 'Curated sample' : session.model} · v
                      {revision.number}
                    </span>
                    <span>
                      {(revision.timings.total_ms / 1000).toFixed(1)}s total{' '}
                      <span className="hint-separator">·</span>{' '}
                      {revision.diagrams.filter((d) => d.cache_hit).length} cached
                    </span>
                  </div>
                </div>
                <div className="artifact-footer">
                  <div className="review-prompt">
                    <span className="review-icon">
                      <ThumbsUp size={17} />
                    </span>
                    <div>
                      <strong>A better design starts with your perspective.</strong>
                      <span>
                        {reviews.length
                          ? `${reviews.length} review${reviews.length === 1 ? '' : 's'} saved · ART ${reviews.at(-1)!.training_status}`
                          : 'Share a review to guide the next iteration.'}
                      </span>
                    </div>
                  </div>
                  <div className="footer-buttons">
                    <button className="secondary" onClick={openReview}>
                      Review design
                    </button>
                    <a className="primary" href={`/api/revisions/${revision.id}/export`} download>
                      <ArrowDownToLine size={15} />
                      Export ZIP
                    </a>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
        <footer className="app-footer">
          <span>THOUGHTFUL SYSTEMS START HERE.</span>
          <span>
            {session.mode === 'sample'
              ? 'Sample mode is deterministic. Configure a provider for your own prompts.'
              : 'AI-assisted architecture. Review assumptions before implementation.'}
          </span>
        </footer>
      </main>
      {toast && (
        <div className="toast" role="status">
          <Check size={16} />
          {toast}
          <button aria-label="Dismiss notification" onClick={() => setToast('')}>
            <X size={14} />
          </button>
        </div>
      )}
      <dialog
        aria-labelledby="modal-title"
        ref={modalRef}
        className={`modal ${modal === 'diagrams' ? 'catalog-modal' : ''}`}
        onCancel={(event) => {
          event.preventDefault();
          if (!reviewBusy) setModal(null);
        }}
        onClick={(e) => {
          if (e.target === modalRef.current && !reviewBusy) setModal(null);
        }}
      >
        <div className="modal-inner">
          <button
            className="modal-close icon-button"
            aria-label="Close dialog"
            onClick={() => setModal(null)}
            disabled={reviewBusy}
          >
            <X size={19} />
          </button>
          {modal === 'diagrams' && (
            <DiagramPicker
              catalog={session.diagram_types}
              selected={types}
              onChange={setTypes}
              onDone={() => setModal(null)}
            />
          )}
          {modal === 'review' && revision && (
            <ReviewForm
              key={revision.id}
              revision={revision}
              catalog={session.diagram_types}
              onBusy={setReviewBusy}
              onReviewed={(review) => {
                setReviews((previous) => [
                  ...previous.filter((item) => item.id !== review.id),
                  review,
                ]);
                setModal(null);
                setToast(
                  'Review saved and queued for ART. It will also inform your next live revision.',
                );
              }}
            />
          )}
          {modal === 'help' && <HelpGuide session={session} />}
        </div>
      </dialog>
    </div>
  );
}
