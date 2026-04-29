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

  // opts를 ref로 관리 — 매 렌더마다 새 객체가 생성되어도 effect가 재실행되지 않도록 함
  const optsRef = useRef(opts);
  useEffect(() => { optsRef.current = opts; });

  const start = useCallback(() => {
    if (!optsRef.current.dirHandle) return;
    stoppedRef.current = false;
    setRunning(true);
  }, []);

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
    if (!running) return;

    const scan = async () => {
      const { dirHandle, extensions, batchSize, onBatch, intervalMs: _ } = optsRef.current;
      if (!dirHandle || processingRef.current) return;

      // processingRef를 파일 수집 전에 잠금 — 수집 중 동시 scan 진입 차단
      processingRef.current = true;
      try {
        const exts = extensions ?? DEFAULT_EXTS;
        const size = batchSize ?? 50;

        // 1. 신규 파일 전부 수집
        const newFiles: WatchedFile[] = [];
        for await (const [name, handle] of (dirHandle as any).entries() as AsyncIterable<
          [string, FileSystemHandle]
        >) {
          if (stoppedRef.current) break;
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
        for (let i = 0; i < newFiles.length; i += size) {
          if (stoppedRef.current) break;
          await onBatch(newFiles.slice(i, i + size));
        }
      } finally {
        processingRef.current = false;
      }
    };

    void scan();
    timerRef.current = window.setInterval(scan, optsRef.current.intervalMs ?? 3000);
    return () => {
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
      timerRef.current = null;
    };
  }, [running]); // opts는 ref로 관리하므로 의존성에서 제외

  return { running, start, stop };
}
