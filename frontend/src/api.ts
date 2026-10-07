import type { DiagramKind, Revision } from './types';

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-Forma-Request': '1', ...init?.headers },
  });
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: 'The server could not complete this request.' }));
    throw new Error(
      typeof error.detail === 'string' ? error.detail : 'Please check the request and try again.',
    );
  }
  return response.json();
}

export interface GeneratePayload {
  prompt: string;
  diagram_types: DiagramKind[];
  conversation_id?: string;
  base_revision?: number;
  request_id: string;
}
export async function generate(
  payload: GeneratePayload,
  signal: AbortSignal,
  onPhase: (message: string) => void,
): Promise<Revision> {
  const response = await fetch('/api/generate', {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json', 'X-Forma-Request': '1' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const e = await response.json();
    throw new Error(typeof e.detail === 'string' ? e.detail : 'The request is invalid.');
  }
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Streaming is unavailable. Please retry.');
  const decoder = new TextDecoder();
  let buffer = '';
  let result: Revision | null = null;
  try {
    while (true) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const events = buffer.split('\n\n');
      buffer = events.pop() ?? '';
      for (const block of events) {
        const lines = block.split('\n');
        const event = lines.find((l) => l.startsWith('event: '))?.slice(7);
        const data = lines
          .filter((l) => l.startsWith('data: '))
          .map((l) => l.slice(6))
          .join('\n');
        if (!data) continue;
        const parsed = JSON.parse(data);
        if (event === 'phase') onPhase(parsed.message);
        if (event === 'error') throw new Error(parsed.message);
        if (event === 'complete') result = parsed;
      }
      if (done) break;
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
  if (!result)
    throw new Error(
      'The connection closed before the design completed. Retry or reload to check saved revisions.',
    );
  return result;
}
export function download(content: string, name: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
