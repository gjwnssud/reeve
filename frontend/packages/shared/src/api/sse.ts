import { fetchEventSource, type EventSourceMessage } from '@microsoft/fetch-event-source';

export type SSEOptions = {
  method?: 'GET' | 'POST';
  headers?: HeadersInit;
  body?: BodyInit | null;
  signal: AbortSignal;
  onEvent: (msg: EventSourceMessage) => void;
  onError?: (err: unknown) => void;
  onOpen?: () => void;
  retry?: { maxAttempts: number; delayMs: number } | false;
};

export async function createSSESubscription(url: string, opts: SSEOptions): Promise<void> {
  const retryMode = opts.retry ?? { maxAttempts: 5, delayMs: 1000 };
  let attempts = 0;
  await fetchEventSource(url, {
    method: opts.method ?? 'GET',
    headers: opts.headers as Record<string, string> | undefined,
    body: opts.body ?? undefined,
    signal: opts.signal,
    openWhenHidden: true,
    onopen: async (res) => {
      if (!res.ok) throw new Error(`SSE open failed: ${res.status}`);
      attempts = 0;
      opts.onOpen?.();
    },
    onmessage: (msg) => opts.onEvent(msg),
    onerror: (err) => {
      attempts += 1;
      if (retryMode === false || attempts > retryMode.maxAttempts) {
        opts.onError?.(err);
        throw err;
      }
      const delay = retryMode.delayMs * Math.pow(2, attempts - 1);
      return delay;
    },
    onclose: () => {
      if (retryMode === false) return;
      if (attempts > retryMode.maxAttempts) return;
      throw new Error('SSE closed — retrying');
    },
  });
}
