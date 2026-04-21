import { useCallback, useEffect, useRef, useState } from 'react';

export type WatchedFile = { name: string; handle: FileSystemFileHandle; file: File };

export type UseFolderWatchOptions = {
  dirHandle: FileSystemDirectoryHandle | null;
  intervalMs?: number;
  extensions?: Set<string>;
  batchSize?: number;
  onBatch: (files: WatchedFile[]) => Promise<void>;
};

const DEFAULT_EXTS = new Set(['jpg', 'jpeg', 'png', 'webp', 'gif', 'bmp', 'avif', 'tiff', 'tif']);

export function useFolderWatch(opts: UseFolderWatchOptions) {
  const [running, setRunning] = useState(false);
  const seen = useRef(new Set<string>());
  const timerRef = useRef<number | null>(null);
  const processingRef = useRef(false);
  const stoppedRef = useRef(false);

  const start = useCallback(() => {
    if (!opts.dirHandle) return;
    stoppedRef.current = false;
    setRunning(true);
  }, [opts.dirHandle]);

  const stop = useCallback(() => {
    stoppedRef.current = true;
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
    const batchSize = opts.batchSize ?? 50;

    const scan = async () => {
      if (!opts.dirHandle || processingRef.current) return;

      // 1. 신규 파일 전부 수집
      const newFiles: WatchedFile[] = [];
      for await (const [name, handle] of (opts.dirHandle as any).entries() as AsyncIterable<
        [string, FileSystemHandle]
      >) {
        if (handle.kind !== 'file') continue;
        if (seen.current.has(name)) continue;
        const ext = name.split('.').pop()?.toLowerCase() ?? '';
        seen.current.add(name);
        if (!exts.has(ext)) continue;
        const fileHandle = handle as FileSystemFileHandle;
        const file = await fileHandle.getFile();
        if (file.type.startsWith('image/')) newFiles.push({ name, handle: fileHandle, file });
      }

      if (newFiles.length === 0) return;

      // 2. 배치 단위로 순차 처리 (각 배치 완료 후 다음 배치)
      processingRef.current = true;
      try {
        for (let i = 0; i < newFiles.length; i += batchSize) {
          if (stoppedRef.current) break;
          await opts.onBatch(newFiles.slice(i, i + batchSize));
        }
      } finally {
        processingRef.current = false;
      }
    };

    void scan();
    timerRef.current = window.setInterval(scan, opts.intervalMs ?? 3000);
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [running, opts]);

  return { running, start, stop };
}
