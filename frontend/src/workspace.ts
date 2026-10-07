import type { GeneratePayload } from './api';
import type { DiagramKind } from './types';

export interface Draft {
  prompt: string;
  types: DiagramKind[];
  mode: 'sample' | 'live';
  pending?: GeneratePayload;
}
const PREFIX = 'forma.draft.v1.';
export function readDraft(id: string): Draft | null {
  try {
    const d = JSON.parse(localStorage.getItem(PREFIX + id) ?? 'null');
    return d &&
      typeof d.prompt === 'string' &&
      Array.isArray(d.types) &&
      ['sample', 'live'].includes(d.mode)
      ? d
      : null;
  } catch {
    return null;
  }
}
export function saveDraft(id: string, draft: Draft) {
  try {
    localStorage.setItem(PREFIX + id, JSON.stringify(draft));
  } catch {
    /* Browsers may disallow local storage. The current draft stays usable. */
  }
}
export function readSource(id: string, fallback: string): string {
  try {
    return localStorage.getItem('forma.source.v1.' + id) ?? fallback;
  } catch {
    return fallback;
  }
}
export function saveSource(id: string, source: string) {
  try {
    localStorage.setItem('forma.source.v1.' + id, source);
  } catch {
    /* Source download remains available. */
  }
}

export const STARTERS = [
  {
    title: 'A resilient payments flow',
    category: 'FINTECH',
    prompt:
      'Design a payment orchestration system for a SaaS marketplace. Customers pay through a payment provider. Record idempotent payment intents, verify signed webhooks, reconcile settlements, handle duplicate events and provider failures, and expose an operations dashboard. Separate sensitive card data from our system. Include evidence for reconciliation and human review for unresolved failures.',
  },
  {
    title: 'Support that keeps context',
    category: 'AI SYSTEMS',
    prompt:
      'Design an AI customer support assistant with a chat interface, retrieval over approved help articles, a tool gateway for order lookups, explicit permissions, conversation storage, and human escalation. Cite retrieved evidence, avoid guessing when sources are missing, redact sensitive logs, and keep a feedback loop for improving responses. Show boundaries for model calls, retrieval, tools, and human review.',
  },
  {
    title: 'A reliable document pipeline',
    category: 'DATA PLATFORM',
    prompt:
      'Design a document processing platform. Users upload files to private object storage; an API creates a job; a durable queue feeds workers that extract text, classify documents, and save searchable results. Include tenant access checks, retries, a dead-letter queue, idempotent jobs, provenance, and a reviewer workflow for low-confidence extraction. Notify users when processing finishes.',
  },
];
