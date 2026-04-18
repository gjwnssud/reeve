import type { IdentificationResult } from './types';

export type StatusInput = {
  status?: string | null;
  error?: string | null;
  yolo_detected?: boolean;
  message?: string | null;
};

export type ResolvedStatus = {
  label: string;
  className: string;
  title?: string;
};

export function resolveStatus(input: StatusInput): ResolvedStatus {
  if (input.error) {
    return { label: '오류', className: 'bg-red-600 text-white', title: input.error };
  }
  switch (input.status) {
    case 'identified':
      return { label: '판별 완료', className: 'bg-emerald-600 text-white' };
    case 'low_confidence':
      return {
        label: '신뢰도 낮음',
        className: 'bg-amber-500 text-white',
        title: input.message ?? undefined,
      };
    case 'no_match':
      return {
        label: '매칭 없음',
        className: 'bg-slate-500 text-white',
        title: input.message ?? undefined,
      };
    default:
      if (input.yolo_detected === false) {
        return { label: '차량 미감지', className: 'bg-slate-400 text-white' };
      }
      return { label: '대기', className: 'bg-slate-300 text-slate-800' };
  }
}

export function resolveResultStatus(result: IdentificationResult): ResolvedStatus {
  return resolveStatus({
    status: result.status,
    message: result.message,
    yolo_detected: result.detection != null,
  });
}
