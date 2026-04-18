import { ApiError, apiRequest } from '@reeve/shared';

import type { Bbox, DetectionResult, IdentificationResult } from './types';

export async function postDetect(file: File): Promise<DetectionResult> {
  const form = new FormData();
  form.append('file', file);
  return apiRequest<DetectionResult>('/detect', { method: 'POST', body: form });
}

export async function postIdentify(
  file: File,
  bbox: Bbox | null,
): Promise<IdentificationResult> {
  const form = new FormData();
  form.append('file', file);
  if (bbox) form.append('bbox', bbox.join(','));
  return apiRequest<IdentificationResult>('/identify', { method: 'POST', body: form });
}

export function extractErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: unknown } | string | null;
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') {
      return body.detail;
    }
    if (typeof body === 'string' && body.trim()) return body;
    return `HTTP ${err.status}`;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
