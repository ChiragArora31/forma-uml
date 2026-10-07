import type { DiagramKind, Revision } from './types';

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
async function responseError(response: Response) {
  const payload = await response.json().catch(() => null);
  const fallback =
    response.status >= 500
      ? 'The service is taking a moment to recover. Your saved work is safe; please retry.'
      : 'Please check the request and try again.';
  return new ApiError(
    typeof payload?.detail === 'string' ? payload.detail : fallback,
    response.status,
  );
}
export async function exportFile(path: string, name: string) {
  const response = await fetch(`/api${path}`);
  if (!response.ok) throw await responseError(response);
  downloadBlob(await response.blob(), name);
}
export function downloadBlob(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function downloadPng(svg: string, name: string) {
  const image = new Image();
  image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await image.decode();
  const scale = Math.min(2, 4096 / image.naturalWidth, 4096 / image.naturalHeight);
  const canvas = document.createElement('canvas');
  canvas.width = Math.ceil(image.naturalWidth * scale);
  canvas.height = Math.ceil(image.naturalHeight * scale);
  const context = canvas.getContext('2d');
  if (!context)
    throw new Error('PNG export is unavailable in this browser. Use SVG or ZIP instead.');
  context.fillStyle = '#ffffff';
  context.fillRect(0, 0, canvas.width, canvas.height);
  context.drawImage(image, 0, 0, canvas.width, canvas.height);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
  if (!blob) throw new Error('The image could not be exported. Please use SVG instead.');
  downloadBlob(blob, name);
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', 'X-Forma-Request': '1', ...init?.headers },
  });
  if (!response.ok) {
    throw await responseError(response);
  }
  return response.json();
}

export interface GeneratePayload {
  prompt: string;
  diagram_types: DiagramKind[];
  conversation_id?: string;
  base_revision?: number;
  request_id: string;
  mode?: 'sample' | 'live';
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
    throw await responseError(response);
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
  downloadBlob(new Blob([content], { type }), name);
}
