import { apiRequest } from '@reeve/shared';

export type Bbox = [number, number, number, number];

export interface Detection {
  bbox: Bbox;
  confidence?: number;
  class_name?: string;
  area?: number;
  [k: string]: unknown;
}

export interface UploadResponse {
  analyzed_id: number;
  original_image_path: string;
}

export interface DetectResponse {
  detections: Detection[];
  count: number;
  image_size: { width: number; height: number };
}

export interface AnalyzeResult {
  id: number;
  manufacturer: string | null;
  model: string | null;
  year: string | null;
  confidence_score: number;
  matched_manufacturer_id: number | null;
  matched_model_id: number | null;
}

export type AnalyzeSSEEvent =
  | { event: 'progress'; progress: number; message: string }
  | { event: 'completed'; progress: 100; result: AnalyzeResult }
  | { event: 'error'; message: string };

export async function uploadFile(
  file: File,
  source: 'file' | 'folder',
  clientUuid: string,
): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  form.append('source', source);
  form.append('client_uuid', clientUuid);
  return apiRequest<UploadResponse>('/api/upload', { method: 'POST', body: form });
}

export interface ServerFileInfo {
  name: string;
  path: string;
}

export async function listServerFiles(dirPath: string): Promise<{ files: ServerFileInfo[] }> {
  return apiRequest<{ files: ServerFileInfo[] }>(
    `/api/server-files?path=${encodeURIComponent(dirPath)}`,
  );
}

export async function registerServerFile(
  filePath: string,
  clientUuid: string,
): Promise<UploadResponse> {
  return apiRequest<UploadResponse>('/api/server-files/register', {
    method: 'POST',
    body: { file_path: filePath, source: 'server', client_uuid: clientUuid },
  });
}

export async function detectVehicle(analyzedId: number): Promise<DetectResponse> {
  const form = new FormData();
  form.append('analyzed_id', String(analyzedId));
  return apiRequest<DetectResponse>('/api/detect-vehicle', { method: 'POST', body: form });
}

export async function* streamAnalyze(
  analyzedId: number,
  bbox: Bbox,
): AsyncGenerator<AnalyzeSSEEvent, void, undefined> {
  const form = new FormData();
  form.append('analyzed_id', String(analyzedId));
  form.append('bbox', JSON.stringify(bbox));

  const res = await fetch('/api/analyze-vehicle-stream', { method: 'POST', body: form });
  if (!res.ok || !res.body) {
    let detail = `HTTP ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload) continue;
        try {
          yield JSON.parse(payload) as AnalyzeSSEEvent;
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  }
}
