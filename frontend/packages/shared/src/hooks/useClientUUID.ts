import { useState } from 'react';

import { STORAGE_KEYS } from '../utils/storage';
import { generateUUID } from '../utils/uuid';

export function useClientUUID(): string {
  const [uuid] = useState<string>(() => {
    if (typeof window === 'undefined') return generateUUID();
    const existing = window.localStorage.getItem(STORAGE_KEYS.clientUUID);
    if (existing) return existing;
    const next = generateUUID();
    window.localStorage.setItem(STORAGE_KEYS.clientUUID, next);
    return next;
  });
  return uuid;
}
