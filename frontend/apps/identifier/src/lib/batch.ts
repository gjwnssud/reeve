import { createSSESubscription } from '@reeve/shared';

import type { IdentificationResult, VehicleDetection } from './types';

export type BatchStage = 'queued' | 'detecting' | 'classifying' | 'done' | 'error';

export type BatchRow = {
  index: number;
  file: File;
  thumbnailUrl: string | null;
  stage: BatchStage;
  status?: string;
  manufacturer_korean?: string | null;
  model_korean?: string | null;
  confidence?: number;
  message?: string;
  detection?: VehicleDetection | null;
  error?: string;
};

export type StreamEvent =
  | { stage: 'detecting'; message?: string }
  | { stage: 'classifying'; message?: string; detection?: VehicleDetection | null }
  | ({ stage: 'done' } & IdentificationResult)
  | { stage: 'error'; message: string };

const IMAGE_EXT = /\.(jpe?g|png|webp)$/i;

export function filterImages(list: FileList): File[] {
  const out: File[] = [];
  for (let i = 0; i < list.length; i += 1) {
    const f = list.item(i);
    if (!f) continue;
    if (f.type.startsWith('image/') || IMAGE_EXT.test(f.name)) out.push(f);
  }
  return out;
}

export function formatSeconds(s: number): string {
  if (!Number.isFinite(s) || s < 0) return '-';
  if (s < 60) return `${s}초`;
  const m = Math.floor(s / 60);
  const rem = s % 60;
  if (m < 60) return rem === 0 ? `${m}분` : `${m}분 ${rem}초`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return mm === 0 ? `${h}시간` : `${h}시간 ${mm}분`;
}

export async function streamIdentify(
  file: File,
  onEvent: (event: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const form = new FormData();
  form.append('file', file);

  await createSSESubscription('/identify/stream', {
    method: 'POST',
    body: form,
    signal,
    retry: false,
    onEvent: (msg) => {
      if (!msg.data) return;
      try {
        const parsed = JSON.parse(msg.data) as StreamEvent;
        onEvent(parsed);
      } catch (err) {
        onEvent({ stage: 'error', message: `SSE 파싱 실패: ${String(err)}` });
      }
    },
    onError: (err) => {
      if (signal.aborted) return;
      const message = err instanceof Error ? err.message : String(err);
      onEvent({ stage: 'error', message });
    },
  });
}

function csvEscape(value: unknown): string {
  if (value == null) return '';
  const s = String(value);
  if (/[",\n]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

export function toCsv(rows: BatchRow[]): string {
  const header = ['#', '파일명', '제조사', '모델', '신뢰도', '상태', '메시지'];
  const lines = [header.join(',')];
  rows.forEach((row, i) => {
    const status = row.error
      ? `error: ${row.error}`
      : (row.status ?? row.stage);
    const conf =
      row.confidence != null && !row.error
        ? `${(row.confidence * 100).toFixed(1)}%`
        : '';
    lines.push(
      [
        i + 1,
        csvEscape(row.file.name),
        csvEscape(row.manufacturer_korean ?? ''),
        csvEscape(row.model_korean ?? ''),
        conf,
        csvEscape(status),
        csvEscape(row.message ?? ''),
      ].join(','),
    );
  });
  return lines.join('\n');
}

export function downloadCsv(csv: string, filename = 'batch_results.csv'): void {
  const BOM = '\ufeff';
  const blob = new Blob([BOM + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
