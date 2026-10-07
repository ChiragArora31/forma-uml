import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertCircle,
  Archive,
  ArrowDownToLine,
  PanelLeft,
  Pencil,
  RotateCcw,
  FileText,
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
import { api, download, downloadPng, exportFile, generate } from './api';
import type { GeneratePayload } from './api';
import type {
  Allowance,
  Conversation,
  ConversationSummary,
  DiagramKind,
  Feedback,
  Session,
} from './types';
import DiagramCanvas from './DiagramCanvas';
import HelpGuide from './HelpGuide';
import DiagramPicker from './DiagramPicker';
import ReviewForm from './ReviewForm';
import WorkspaceSettings from './WorkspaceSettings';
import { revisionChanges } from './changes';
import { readDraft, saveDraft, readSource, saveSource, STARTERS } from './workspace';

type View = 'diagram' | 'source' | 'notes' | 'compare';
type Modal = 'diagrams' | 'review' | 'help' | 'manage' | 'workspace' | 'starters' | null;
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

export default function App() {
  const [session, setSession] = useState<Session | null>(null);
  const [hydrated, setHydrated] = useState(false);
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
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState('');
  const [toast, setToastMessage] = useState('');
  const [toastTone, setToastTone] = useState<'success' | 'info' | 'error'>('success');
  function setToast(message: string, tone: 'success' | 'info' | 'error' = 'success') {
    setToastMessage(message);
    setToastTone(tone);
  }
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const [archived, setArchived] = useState(false);
  const [opening, setOpening] = useState(false);
  const [requestMode, setRequestMode] = useState<'sample' | 'live'>('sample');
  const [allowance, setAllowance] = useState<Allowance | null>(null);
  const [undoArchive, setUndoArchive] = useState<string | null>(null);
  const [source, setSource] = useState('');
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [sourceBusy, setSourceBusy] = useState(false);
  const [exportBusy, setExportBusy] = useState(false);
  const [sourceError, setSourceError] = useState('');
  const [modalBusy, setModalBusy] = useState(false);
  const [reviews, setReviews] = useState<Feedback[]>([]);
  const [bootError, setBootError] = useState('');
  const controller = useRef<AbortController | null>(null);
  const pending = useRef<{ payload: GeneratePayload; prompt: string } | null>(null);
  const sourceController = useRef<AbortController | null>(null);
  const openController = useRef<AbortController | null>(null);
  const listController = useRef<AbortController | null>(null);
  const archivedRef = useRef(archived);
  archivedRef.current = archived;
  const feed = useRef<HTMLDivElement>(null);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const modalRef = useRef<HTMLDialogElement>(null);
  const revision = conversation?.revisions[revisionIndex] ?? null;
  const diagram = revision?.diagrams.find((d) => d.type === kind) ?? revision?.diagrams[0];
  const label = (k: DiagramKind) => session?.diagram_types.find((d) => d.id === k)?.label ?? k;

  const refresh = useCallback(async () => {
    listController.current?.abort();
    const abort = new AbortController();
    listController.current = abort;
    try {
      const items = await api<ConversationSummary[]>(
        `/conversations?archived=${archivedRef.current}`,
        { signal: abort.signal },
      );
      if (!abort.signal.aborted) setConversations(items);
    } catch (e) {
      if ((e as Error).name !== 'AbortError') throw e;
    }
  }, []);
  const previous =
    conversation && revisionIndex > 0 ? conversation.revisions[revisionIndex - 1] : null;
  const changes = useMemo(
    () => (previous && revision ? revisionChanges(previous, revision) : []),
    [previous, revision],
  );
  function restoreDraft(c: Conversation | null, currentSession: Session) {
    const d = readDraft(c?.id ?? 'new');
    setPrompt(d?.prompt ?? '');
    const validTypes =
      d?.types.filter((t) => currentSession.diagram_types.some((k) => k.id === t)) ?? [];
    setTypes(
      validTypes.length
        ? validTypes
        : (c?.revisions.at(-1)?.diagrams.map((d) => d.type) ?? DEFAULT_TYPES),
    );
    setRequestMode(
      currentSession.mode === 'sample'
        ? 'sample'
        : c?.revisions.at(-1)?.mode === 'live'
          ? 'live'
          : (d?.mode ?? (c?.revisions.at(-1)?.mode === 'sample' ? 'sample' : 'live')),
    );
    pending.current = d?.pending ? { payload: d.pending, prompt: d.prompt } : null;
  }
  useEffect(() => {
    let alive = true;
    const abort = new AbortController();
    void api<Session>('/session', { signal: abort.signal })
      .then(async (current) => {
        if (!alive) return;
        setSession(current);
        const [items, available] = await Promise.all([
          api<ConversationSummary[]>('/conversations', { signal: abort.signal }),
          api<Allowance>('/allowance', { signal: abort.signal }),
        ]);
        if (!alive) return;
        setConversations(items);
        setAllowance(available);
        const id = location.hash.match(/^#design\/([0-9a-f-]{36})$/)?.[1];
        if (id) {
          try {
            const c = await api<Conversation>(`/conversations/${id}`, { signal: abort.signal });
            if (!alive) return;
            setConversation(c);
            setRevisionIndex(c.revisions.length - 1);
            restoreDraft(c, current);
          } catch (e) {
            if (alive) {
              setError(
                'This design is unavailable in this browser. Open a saved design or start a new one.',
              );
              restoreDraft(null, current);
            }
          }
        } else restoreDraft(null, current);
        if (alive) setHydrated(true);
      })
      .catch((e) => {
        if (alive && e.name !== 'AbortError') setBootError(e.message);
      });
    return () => {
      alive = false;
      abort.abort();
      controller.current?.abort();
      sourceController.current?.abort();
      openController.current?.abort();
    };
  }, []);
  useEffect(() => {
    if (session && hydrated) void refresh().catch((e) => setError(e.message));
  }, [archived, refresh, session, hydrated]);
  useEffect(() => {
    if (!session || !hydrated) return;
    const id = conversation?.id ?? 'new';
    const timer = setTimeout(
      () => saveDraft(id, { prompt, types, mode: requestMode, pending: pending.current?.payload }),
      200,
    );
    return () => clearTimeout(timer);
  }, [prompt, types, requestMode, conversation?.id, session, busy, hydrated]);
  useEffect(() => {
    if (!session || !hydrated) return;
    history.replaceState(
      null,
      '',
      conversation ? '#design/' + conversation.id : location.pathname + location.search,
    );
  }, [conversation?.id, session, hydrated]);
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
    sourceController.current?.abort();
    sourceController.current = null;
    setSourceBusy(false);
    setSource(
      diagram && revision ? readSource(`${revision.id}:${diagram.type}`, diagram.source) : '',
    );
    setSourcePreview(null);
    setSourceError('');
  }, [revision?.id, diagram?.type]);
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
  }, [revision?.id]);
  useEffect(() => {
    const dialog = modalRef.current;
    if (modal && dialog && !dialog.open) dialog.showModal();
    else if (!modal && dialog?.open) dialog.close();
  }, [modal]);
  useEffect(() => {
    function escape(e: KeyboardEvent) {
      if (modalRef.current?.open) return;
      if (e.key === 'Escape') setExpanded(false);
      if (e.key === 'Tab' && expanded) {
        const panel = document.querySelector<HTMLElement>('.artifact-panel.expanded');
        const focusable = Array.from(
          panel?.querySelectorAll<HTMLElement>('button, a, select, textarea, [tabindex]') ?? [],
        ).filter(
          (el) => el.tabIndex >= 0 && !el.hasAttribute('disabled') && el.offsetParent !== null,
        );
        const first = focusable[0],
          last = focusable.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    }
    window.addEventListener('keydown', escape);
    return () => window.removeEventListener('keydown', escape);
  }, [expanded]);
  useEffect(() => {
    if (!busy) return;
    const start = performance.now();
    setElapsed(0);
    const timer = setInterval(
      () => setElapsed(Math.floor((performance.now() - start) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [busy]);

  function reset() {
    if (busy) return;
    saveDraft(conversation?.id ?? 'new', {
      prompt,
      types,
      mode: requestMode,
      pending: pending.current?.payload,
    });
    openController.current?.abort();
    openController.current = null;
    setOpening(false);
    setConversation(null);
    setRevisionIndex(-1);
    setPrompt('');
    setError('');
    setView('diagram');
    setTypes(DEFAULT_TYPES);
    setRequestMode(session?.mode ?? 'sample');
    setExpanded(false);
    setKind('component');
    pending.current = null;
    textarea.current?.focus();
  }
  async function openConversation(id: string) {
    if (busy) return;
    saveDraft(conversation?.id ?? 'new', {
      prompt,
      types,
      mode: requestMode,
      pending: pending.current?.payload,
    });
    openController.current?.abort();
    const abort = new AbortController();
    openController.current = abort;
    setOpening(true);
    try {
      const c = await api<Conversation>(`/conversations/${id}`, { signal: abort.signal });
      if (abort.signal.aborted) return;
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
      if (session) restoreDraft(c, session);
      setExpanded(false);
    } catch (e) {
      if ((e as Error).name !== 'AbortError') setError((e as Error).message);
    } finally {
      if (openController.current === abort) {
        openController.current = null;
        setOpening(false);
      }
    }
  }
  async function send(
    override?: string,
    overrideTypes?: DiagramKind[],
    modeOverride?: 'sample' | 'live',
  ) {
    const input = (override ?? prompt).trim();
    const selectedTypes = overrideTypes ?? types;
    const mode = modeOverride ?? requestMode;
    if (
      !session ||
      busy ||
      opening ||
      input.length < 10 ||
      !selectedTypes.length ||
      conversation?.archived ||
      (mode === 'live' && allowance?.remaining === 0)
    )
      return;
    const latest = conversation?.revisions.at(-1);
    const draft: GeneratePayload = {
      prompt: input,
      mode,
      diagram_types: selectedTypes,
      ...(conversation ? { conversation_id: conversation.id, base_revision: latest!.number } : {}),
      request_id: crypto.randomUUID(),
    };
    // A retry of the exact same action reuses its ID, including after a network failure.
    const old = pending.current?.payload;
    const same =
      old &&
      old.prompt === draft.prompt &&
      old.mode === draft.mode &&
      old.conversation_id === draft.conversation_id &&
      old.base_revision === draft.base_revision &&
      old.diagram_types.join() === draft.diagram_types.join();
    const payload = same ? old : draft;
    pending.current = { payload, prompt: input };
    saveDraft(conversation?.id ?? 'new', {
      prompt: input,
      types: selectedTypes,
      mode,
      pending: payload,
    });
    setRequestMode(mode);
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
      saveDraft(conversation?.id ?? 'new', { prompt: '', types: selectedTypes, mode });
      saveDraft(c.id, { prompt: '', types: selectedTypes, mode });
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
      void api<Allowance>('/allowance')
        .then(setAllowance)
        .catch(() => undefined);
    }
  }
  async function validateSource() {
    sourceController.current?.abort();
    const abort = new AbortController();
    sourceController.current = abort;
    setSourceBusy(true);
    setSourceError('');
    try {
      const r = await api<{ svg: string }>('/render', {
        method: 'POST',
        signal: abort.signal,
        body: JSON.stringify({ source }),
      });
      if (sourceController.current !== abort) return;
      setSourcePreview(r.svg);
      setToast('Syntax checked. This is a local preview; the saved revision is unchanged.');
    } catch (e) {
      if ((e as Error).name !== 'AbortError' && sourceController.current === abort) {
        setSourceError((e as Error).message);
        setSourcePreview(null);
      }
    } finally {
      if (sourceController.current === abort) {
        setSourceBusy(false);
        sourceController.current = null;
      }
    }
  }
  async function takeExport(format: 'zip' | 'report' | 'png') {
    if (!revision || !diagram || exportBusy) return;
    setExportBusy(true);
    try {
      if (format === 'png')
        await downloadPng(
          sourcePreview ?? diagram.svg,
          `${diagram.type}${sourcePreview ? '-preview' : ''}.png`,
        );
      else
        await exportFile(
          `/revisions/${revision.id}/${format === 'zip' ? 'export' : 'report'}`,
          format === 'zip'
            ? `forma-revision-${revision.number}.zip`
            : `forma-review-v${revision.number}.md`,
        );
      setToast(
        format === 'zip'
          ? 'Export ready: diagrams, editable source, the design brief, and reviews.'
          : format === 'png'
            ? 'PNG exported at up to 2× resolution.'
            : 'Design review brief exported.',
      );
    } catch (e) {
      setToast((e as Error).message, 'error');
    } finally {
      setExportBusy(false);
    }
  }
  async function copySource() {
    try {
      await navigator.clipboard.writeText(source);
      setToast('PlantUML source copied');
    } catch {
      setToast('Clipboard unavailable. Use the source download instead.', 'info');
    }
  }
  async function restoreArchived(id: string) {
    try {
      const c = await api<Conversation>(`/conversations/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ archived: false }),
      });
      setArchived(false);
      setUndoArchive(null);
      setConversation(c);
      setRevisionIndex(c.revisions.length - 1);
      if (session) restoreDraft(c, session);
      setToast('Design restored. All revisions are ready to explore.');
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function startBrief(brief: string) {
    modalRef.current?.close();
    setModal(null);
    setPrompt(brief);
    setRequestMode('live');
    textarea.current?.focus();
    textarea.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
  if (!session || !hydrated)
    return (
      <div className="boot-error">
        <Mark />
        <Loader2 className="spin" />
        <p>Opening your workspace…</p>
      </div>
    );
  const isHistoric = conversation && revisionIndex < conversation.revisions.length - 1;
  const briefLength = prompt.trim().length;
  const sendDisabledReason = busy
    ? 'Your design is being generated.'
    : opening
      ? 'Opening this design…'
      : conversation?.archived
        ? 'Restore this design to enter a new request.'
        : briefLength === 0
          ? 'Type your brief above (at least 10 characters) to enable Send.'
          : briefLength < 10
            ? `Add ${10 - briefLength} more character${10 - briefLength === 1 ? '' : 's'} to enable Send.`
            : !types.length
              ? 'Choose at least one UML view to enable Send.'
              : requestMode === 'live' && allowance?.remaining === 0
                ? 'Today’s free AI allowance is used. You can explore a new case study.'
                : '';

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
          <span>{archived ? 'ARCHIVED DESIGNS' : 'YOUR WORKSPACE'}</span>
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
        <button
          className="archive-toggle"
          onClick={() => {
            setArchived((v) => !v);
            setQuery('');
          }}
        >
          <Archive size={13} />
          {archived ? 'Back to active designs' : 'Show archived designs'}
        </button>
        <nav className="design-list" aria-label="Saved designs">
          {conversations
            .filter((c) => c.title.toLowerCase().includes(query.toLowerCase()))
            .map((c) => (
              <button
                key={c.id}
                aria-label={`${c.title} ${c.latest} revision${c.latest === 1 ? '' : 's'}`}
                title={c.title}
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
              {archived ? 'No archived designs.' : 'Your designs will live here.'}
              <br />
              {archived
                ? 'Keep only what you need in your workspace.'
                : 'Start with a brief below.'}
            </p>
          )}
          {query &&
            conversations.length > 0 &&
            !conversations.some((c) => c.title.toLowerCase().includes(query.toLowerCase())) && (
              <p className="empty-history">
                No designs match “{query}”.
                <button onClick={() => setQuery('')}>Clear search</button>
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
              <strong>
                {session.storage === 'postgres' ? 'Your design workspace' : 'Your local workspace'}
              </strong>
              <small>Private to this browser · drafts saved</small>
            </div>
          </div>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <button
            className="icon-button mobile-workspace"
            aria-label="Open workspace"
            onClick={() => setModal('workspace')}
          >
            <PanelLeft size={19} />
          </button>
          <div className="breadcrumb">
            <span>Workspace</span>
            <ChevronRight size={13} />
            <strong>
              {opening ? 'Opening design…' : (conversation?.title ?? 'Untitled design')}
            </strong>
          </div>
          <div className="top-actions">
            {conversation && (
              <button
                className="icon-button"
                aria-label="Design settings"
                disabled={busy}
                onClick={() => setModal('manage')}
              >
                <Pencil size={16} />
              </button>
            )}
            <span className="mode-indicator">
              <i />
              {session.mode === 'sample' ? 'Case study available' : 'Live AI available'}
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
        <div className={`workspace ${!revision ? 'workspace-empty' : ''}`}>
          <section className="conversation-panel" aria-label="Design conversation">
            <div className="panel-heading">
              <div>
                <MessageSquare size={16} />
                <h2>{conversation ? 'Refine your design' : 'New design'}</h2>
              </div>
              <span className="tiny-label">
                {conversation ? `${conversation.revisions.length} ITERATIONS` : 'LET’S BEGIN'}
              </span>
            </div>
            <div className="conversation-feed" ref={feed}>
              {!conversation && (
                <div className="start-intro">
                  <span className="eyebrow">FROM A BRIEF TO A BLUEPRINT</span>
                  <h1>What would you like to design?</h1>
                  <p>
                    Describe your requirements and constraints. We’ll turn them into a consistent
                    software architecture.
                  </p>
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
                    <details className="request-details">
                      <summary>View your request</summary>
                      <p>{r.prompt}</p>
                    </details>
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
                      {requestMode === 'sample'
                        ? 'Opening a verified case study'
                        : `${types.length} views from one shared architecture · ${elapsed}s elapsed`}
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
              {revision && !busy && !conversation?.archived && (
                <div className="next-steps">
                  <span className="tiny-label">KEEP THE DESIGN MOVING</span>
                  {revision.mode === 'sample' ? (
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
              {conversation?.archived ? (
                <div className="archived-banner">
                  <Archive size={16} />
                  <span>This design is archived. Its history is preserved.</span>
                  <button onClick={() => void restoreArchived(conversation.id)}>
                    <RotateCcw size={13} />
                    Restore
                  </button>
                </div>
              ) : session.mode === 'live' ? (
                <details className="generation-options">
                  <summary aria-label="Generation options">
                    <span>{requestMode === 'live' ? 'Live AI' : 'Curated case study'}</span>
                    <small>
                      {requestMode === 'live'
                        ? `${allowance?.remaining ?? '…'} free attempts available today`
                        : 'Instant example · no AI quota used'}
                    </small>
                    <ChevronDown size={13} />
                  </summary>
                  <div className="generation-choice">
                    <div role="group" aria-label="Generation mode">
                      <button
                        aria-pressed={requestMode === 'live'}
                        disabled={busy}
                        onClick={() => setRequestMode('live')}
                      >
                        Live AI
                      </button>
                      <button
                        aria-pressed={requestMode === 'sample'}
                        disabled={busy || conversation?.revisions.at(-1)?.mode === 'live'}
                        title={
                          conversation?.revisions.at(-1)?.mode === 'live'
                            ? 'Start a new design to explore the curated case study'
                            : 'Use the curated SEBI workflow'
                        }
                        onClick={() => setRequestMode('sample')}
                      >
                        Case study
                      </button>
                    </div>
                    <span>
                      {requestMode === 'live'
                        ? `${allowance?.remaining ?? '…'} AI attempts available today`
                        : 'Instant curated examples · no AI quota used'}
                    </span>
                  </div>
                </details>
              ) : null}
              {isHistoric && (
                <p className="historic-note">
                  <History size={12} /> Viewing v{revision!.number}. New requests update v
                  {conversation!.latest}.
                </p>
              )}
              <div className="selected-types">
                <button
                  className="view-request-button"
                  aria-label="Choose UML diagram types"
                  onClick={() => setModal('diagrams')}
                >
                  <Layers size={13} />
                  {types.length === 2 && types.includes('sequence') && types.includes('component')
                    ? 'Sequence + Component'
                    : `${types.length} UML views`}
                  <ChevronDown size={12} />
                </button>
              </div>
              <div className="composer">
                <label className="composer-label" htmlFor="design-brief">
                  {conversation ? 'Your next request' : 'Your design brief'}
                </label>
                <textarea
                  id="design-brief"
                  ref={textarea}
                  aria-label="Describe your software design"
                  aria-describedby="composer-guidance"
                  placeholder={
                    conversation
                      ? 'What would you like to change?'
                      : 'Describe the system you have in mind…'
                  }
                  value={prompt}
                  maxLength={12000}
                  onChange={(e) => setPrompt(e.target.value)}
                  disabled={busy || !!conversation?.archived || opening}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      void send();
                    }
                  }}
                />
                <div className="composer-footer">
                  <span id="composer-guidance">
                    {sendDisabledReason ||
                      `${prompt.length.toLocaleString()} / 12,000 · Draft saved`}
                  </span>
                  <button
                    className="send-button"
                    aria-label="Send design request"
                    title={sendDisabledReason || 'Send your design request'}
                    disabled={!!sendDisabledReason}
                    onClick={() => void send()}
                  >
                    {busy ? <Loader2 size={17} className="spin" /> : <ArrowUp size={18} />}
                    <span>Send</span>
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
            {!conversation && !busy && (
              <div className="start-examples">
                <span className="tiny-label">TRY AN EXAMPLE BRIEF</span>
                <div className="example-buttons">
                  <button
                    aria-label="Use the assignment brief"
                    onClick={() => {
                      setPrompt(session.sample_prompt);
                      textarea.current?.focus();
                    }}
                  >
                    SEBI compliance
                  </button>
                  {session.mode === 'live' &&
                    STARTERS.map((starter) => (
                      <button key={starter.title} onClick={() => startBrief(starter.prompt)}>
                        {starter.title}
                      </button>
                    ))}
                </div>
                <button
                  className="case-study-link"
                  onClick={() => void send(session.sample_prompt, types, 'sample')}
                  disabled={busy}
                >
                  Open the SEBI case study <ArrowUpRight size={13} />
                </button>
                <p className="case-study-description">
                  A ready-made example to explore without waiting for AI.
                </p>
              </div>
            )}
          </section>

          {revision && (
            <section
              className={`artifact-panel ${expanded ? 'expanded' : ''}`}
              aria-label="Design workspace"
            >
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
                  <label className="diagram-view-select">
                    <Layers size={14} />
                    <select
                      aria-label="Select UML view"
                      value={diagram?.type}
                      onChange={(e) => {
                        setKind(e.target.value as DiagramKind);
                        setView('diagram');
                      }}
                    >
                      {revision.diagrams.map((d) => (
                        <option value={d.type} key={d.type}>
                          {label(d.type)}
                        </option>
                      ))}
                    </select>
                    <ChevronDown size={12} />
                  </label>
                  <span className="view-count">{revision.diagrams.length} verified views</span>
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
                  role="region"
                  aria-label={`${diagram ? label(diagram.type) : 'UML'} view`}
                  tabIndex={0}
                  aria-busy={sourceBusy}
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
                        {view === 'source' && source !== diagram?.source
                          ? sourcePreview
                            ? 'Preview verified'
                            : 'Draft · check syntax'
                          : 'Syntax verified'}
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
                            disabled={source !== diagram?.source && !sourcePreview}
                            title={
                              source !== diagram?.source && !sourcePreview
                                ? 'Check the edited source before downloading its SVG'
                                : 'Download the displayed diagram'
                            }
                            onClick={() =>
                              diagram &&
                              download(
                                sourcePreview ?? diagram.svg,
                                `${diagram.type}${sourcePreview ? '-preview' : ''}.svg`,
                                'image/svg+xml',
                              )
                            }
                          >
                            <ArrowDownToLine size={13} /> .svg
                          </button>
                          <button
                            disabled={exportBusy || (source !== diagram?.source && !sourcePreview)}
                            onClick={() => void takeExport('png')}
                          >
                            <ArrowDownToLine size={13} />
                            .png
                          </button>
                          <button onClick={copySource}>
                            <Copy size={13} /> Copy
                          </button>
                        </div>
                      </div>
                      <textarea
                        aria-label="PlantUML source editor"
                        spellCheck={false}
                        disabled={sourceBusy}
                        value={source}
                        onChange={(e) => {
                          setSource(e.target.value);
                          setSourcePreview(null);
                          if (revision && diagram)
                            saveSource(`${revision.id}:${diagram.type}`, e.target.value);
                        }}
                      />
                      <div className="source-actions">
                        <p>
                          Preview edits are saved in this browser. Generated revisions stay intact.
                          <button
                            className="text-link"
                            onClick={() => {
                              if (diagram && revision) {
                                setSource(diagram.source);
                                saveSource(`${revision.id}:${diagram.type}`, diagram.source);
                                setSourcePreview(null);
                                setSourceError('');
                              }
                            }}
                            disabled={sourceBusy || source === diagram?.source}
                          >
                            Reset to generated source
                          </button>
                        </p>
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
                      <div className="design-facts">
                        <div>
                          <strong>{revision.architecture.components.length}</strong>
                          <span>system boundaries</span>
                        </div>
                        <div>
                          <strong>{revision.architecture.requirements.length}</strong>
                          <span>requirements</span>
                        </div>
                        <div>
                          <strong>{revision.architecture.actors.length}</strong>
                          <span>actor perspectives</span>
                        </div>
                        <div>
                          <strong>{revision.diagrams.length}</strong>
                          <span>verified views</span>
                        </div>
                      </div>
                      <h3>Actors and goals</h3>
                      <div className="boundary-list">
                        {revision.architecture.actors.map((actor) => (
                          <div key={actor.name}>
                            <strong>{actor.name}</strong>
                            <span>{actor.goals.join('; ')}</span>
                          </div>
                        ))}
                      </div>
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
                        Compared with v{previous.number}. A complete comparison across requirements,
                        boundaries, workflows, domain models, and deployment decisions.
                      </p>
                      {changes.length ? (
                        changes.map((change, i) => (
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
                          The system model is unchanged. Only the requested diagram perspectives may
                          differ.
                        </p>
                      )}
                    </div>
                  )}
                  <div className="canvas-status">
                    <span>
                      <span className="status-dot" />
                      PlantUML ·{' '}
                      {revision.mode === 'sample'
                        ? 'Curated case study'
                        : (revision.model ?? session.model)}{' '}
                      · v{revision.number}
                    </span>
                    <span>
                      {(revision.timings.design_ms / 1000).toFixed(1)}s design ·{' '}
                      {(revision.timings.render_ms / 1000).toFixed(1)}s render{' '}
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
                          ? `${reviews.length} review${reviews.length === 1 ? '' : 's'} saved · linked to this revision`
                          : 'Share a review to guide the next iteration.'}
                      </span>
                    </div>
                  </div>
                  <div className="footer-buttons">
                    <a
                      className="report-link"
                      aria-label="Download design review brief"
                      href={`/api/revisions/${revision.id}/report`}
                      aria-disabled={exportBusy}
                      onClick={(e) => {
                        e.preventDefault();
                        void takeExport('report');
                      }}
                      download
                    >
                      <FileText size={15} />
                      <span>Review brief</span>
                    </a>
                    <button className="secondary" onClick={openReview}>
                      Review design
                    </button>
                    <a
                      className="primary"
                      href={`/api/revisions/${revision.id}/export`}
                      download
                      aria-disabled={exportBusy}
                      onClick={(e) => {
                        e.preventDefault();
                        void takeExport('zip');
                      }}
                    >
                      <ArrowDownToLine size={15} />
                      Export ZIP
                    </a>
                  </div>
                </div>
              </>
            </section>
          )}
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
        <div className={`toast toast-${toastTone}`} role="status">
          {toastTone === 'error' ? (
            <AlertCircle size={16} />
          ) : toastTone === 'info' ? (
            <CircleHelp size={16} />
          ) : (
            <Check size={16} />
          )}
          {toast}
          {undoArchive && (
            <button className="toast-action" onClick={() => void restoreArchived(undoArchive)}>
              Undo archive
            </button>
          )}
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
          if (!modalBusy) setModal(null);
        }}
        onClick={(e) => {
          if (e.target === modalRef.current && !modalBusy) setModal(null);
        }}
      >
        <div className="modal-inner">
          <button
            className="modal-close icon-button"
            aria-label="Close dialog"
            onClick={() => setModal(null)}
            disabled={modalBusy}
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
              onBusy={setModalBusy}
              onReviewed={(review) => {
                setReviews((previous) => [
                  ...previous.filter((item) => item.id !== review.id),
                  review,
                ]);
                setModal(null);
                setToast(
                  revision.mode === 'sample'
                    ? 'Review saved with this case-study revision.'
                    : 'Review saved. It will guide your next refinement.',
                );
              }}
            />
          )}
          {modal === 'starters' && (
            <>
              <span className="eyebrow">START WITH AN IDEA</span>
              <h2 id="modal-title">What would you like to map?</h2>
              <p>Pick a useful starting brief, then make it your own before generating.</p>
              <div className="starter-options">
                {STARTERS.map((starter, i) => (
                  <button
                    className="starter-card"
                    key={starter.title}
                    onClick={() => startBrief(starter.prompt)}
                  >
                    <span>{starter.category}</span>
                    <strong>{starter.title}</strong>
                    <p>
                      {
                        [
                          'Idempotency, verified events, and a clear reconciliation boundary.',
                          'Retrieval, safe tool access, and a thoughtful human handoff.',
                          'Private uploads, durable processing, and confident review.',
                        ][i]
                      }
                    </p>
                  </button>
                ))}
              </div>
              <button className="secondary" onClick={() => startBrief('')}>
                Write my own brief
                <ArrowUpRight size={14} />
              </button>
            </>
          )}
          {modal === 'manage' && conversation && (
            <WorkspaceSettings
              conversation={conversation}
              onBusy={setModalBusy}
              onSaved={(c, wasArchived) => {
                setModal(null);
                if (wasArchived) {
                  setUndoArchive(c.id);
                  reset();
                  setToast('Design archived. Every revision is preserved.');
                } else {
                  setConversation(c);
                  setToast('Workspace updated.');
                }
                void refresh().catch((e) => setError(e.message));
              }}
            />
          )}
          {modal === 'workspace' && (
            <>
              <span className="eyebrow">YOUR WORKSPACE</span>
              <h2 id="modal-title">Pick up where you left off.</h2>
              <button
                className="primary"
                disabled={busy}
                onClick={() => {
                  setModal(null);
                  reset();
                }}
              >
                <Plus size={15} />
                New design
              </button>
              <label className="form-label">
                Find a design
                <input value={query} onChange={(e) => setQuery(e.target.value)} />
              </label>
              <button className="archive-toggle" onClick={() => setArchived((v) => !v)}>
                <Archive size={13} />
                {archived ? 'Show active designs' : 'Show archived designs'}
              </button>
              <div className="mobile-design-list">
                {conversations
                  .filter((c) => c.title.toLowerCase().includes(query.toLowerCase()))
                  .map((c) => (
                    <button
                      key={c.id}
                      className="design-item"
                      aria-label={`${c.title} ${c.latest} revision${c.latest === 1 ? '' : 's'}`}
                      disabled={busy}
                      onClick={() => {
                        setModal(null);
                        void openConversation(c.id);
                      }}
                    >
                      <Workflow size={16} />
                      <span>
                        <strong>{c.title}</strong>
                        <small>{c.latest} revisions</small>
                      </span>
                      <ArrowUpRight size={14} />
                    </button>
                  ))}
                {!conversations.filter((c) => c.title.toLowerCase().includes(query.toLowerCase()))
                  .length && <p>No designs here yet.</p>}
              </div>
            </>
          )}
          {modal === 'help' && <HelpGuide session={session} />}
        </div>
      </dialog>
    </div>
  );
}
