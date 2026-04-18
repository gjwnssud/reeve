import { useCallback, useEffect, useRef, useState } from 'react';

import { Semaphore } from '../utils/Semaphore';

export type WatchedFile = { name: string; handle: FileSystemFileHandle; file: File };

export type UseFolderWatchOptions = {
  dirHandle: FileSystemDirectoryHandle | null;
  intervalMs?: number;
  extensions?: Set<string>;
  onNewFile: (file: WatchedFile, release: () => void) => Promise<void> | void;
  concurrency?: number;
};

const DEFAULT_EXTS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'avif', 'tiff', 'tif']);

export function useFolderWatch(opts: UseFolderWatchOptions) {
  const [running, setRunning] = useState(false);
  const seen = useRef(new Set<string>());
  const timerRef = useRef<number | null>(null);
  const semaRef = useRef(new Semaphore(opts.concurrency ?? 4));

  const start = useCallback(() => {
    if (!opts.dirHandle) return;
    setRunning(true);
  }, [opts.dirHandle]);

  const stop = useCallback(() => {
    setRunning(false);
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
    seen.current.clear();
  }, []);

  useEffect(() => {
    if (!running || !opts.dirHandle) return;
    const exts = opts.extensions ?? DEFAULT_EXTS;
    const scan = async () => {
      if (!opts.dirHandle) return;
      for await (const [name, handle] of (opts.dirHandle as any).entries() as AsyncIterable<
        [string, FileSystemHandle]
      >) {
        if (handle.kind !== 'file') continue;
        if (seen.current.has(name)) continue;
        const ext = name.split('.').pop()?.toLowerCase() ?? '';
        if (!exts.has(ext)) {
          seen.current.add(name);
          continue;
        }
        seen.current.add(name);
        const fileHandle = handle as FileSystemFileHandle;
        const file = await fileHandle.getFile();
        const release = await semaRef.current.acquire();
        void Promise.resolve(opts.onNewFile({ name, handle: fileHandle, file }, release));
      }
    };
    void scan();
    timerRef.current = window.setInterval(scan, opts.intervalMs ?? 3000);
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [running, opts]);

  return { running, start, stop, pendingCount: semaRef.current.pending };
}
