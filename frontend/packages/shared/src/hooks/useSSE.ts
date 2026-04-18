import { useEffect, useRef, useState } from 'react';

import { createSSESubscription } from '../api/sse';

export type ConnectionState = 'idle' | 'open' | 'retrying' | 'closed';

export type UseSSEOptions<T> = {
  enabled?: boolean;
  method?: 'GET' | 'POST';
  headers?: HeadersInit;
  body?: BodyInit | null;
  onEvent: (event: { event?: string; data: T }) => void;
  onError?: (err: unknown) => void;
  parse?: (raw: string) => T;
  retry?: { maxAttempts: number; delayMs: number } | false;
};

export function useSSE<T = unknown>(url: string, opts: UseSSEOptions<T>) {
  const [state, setState] = useState<ConnectionState>('idle');
  const abortRef = useRef<AbortController | null>(null);
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    if (opts.enabled === false) return;
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState('open');
    const parse = opts.parse ?? ((raw: string) => JSON.parse(raw) as T);
    createSSESubscription(url, {
      method: opts.method,
      headers: opts.headers,
      body: opts.body,
      signal: ctrl.signal,
      retry: opts.retry,
      onOpen: () => setState('open'),
      onEvent: (msg) => {
        try {
          optsRef.current.onEvent({ event: msg.event, data: parse(msg.data) });
        } catch (e) {
          optsRef.current.onError?.(e);
        }
      },
      onError: (e) => {
        setState('retrying');
        optsRef.current.onError?.(e);
      },
    }).finally(() => setState('closed'));
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, opts.enabled]);

  return {
    connectionState: state,
    abort: () => abortRef.current?.abort(),
  };
}
