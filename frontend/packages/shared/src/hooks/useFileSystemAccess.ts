import { useCallback, useMemo } from 'react';

export type FSASupport = {
  supported: boolean;
  pickDirectory: () => Promise<FileSystemDirectoryHandle | null>;
};

declare global {
  interface Window {
    showDirectoryPicker?: (opts?: { mode?: 'read' | 'readwrite' }) => Promise<FileSystemDirectoryHandle>;
  }
}

export function useFileSystemAccess(): FSASupport {
  const supported = useMemo(
    () => typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function',
    [],
  );
  const pickDirectory = useCallback(async () => {
    if (!supported || !window.showDirectoryPicker) return null;
    try {
      return await window.showDirectoryPicker({ mode: 'readwrite' });
    } catch (e) {
      if ((e as DOMException)?.name === 'AbortError') return null;
      throw e;
    }
  }, [supported]);
  return { supported, pickDirectory };
}
