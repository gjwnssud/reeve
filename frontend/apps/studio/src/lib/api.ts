import { ApiError, apiRequest } from '@reeve/shared';

// ─── Types ─────────────────────────────────────────────────────────────────

export type StatusFilter = 'all' | 'uploaded' | 'yolo_failed' | 'yolo_detected' | 'analysis_complete' | 'verified';

export type ReviewStatus = 'pending' | 'approved' | 'on_hold' | 'rejected';

export type ReviewSort = 'created_desc' | 'created_asc' | 'confidence_desc' | 'confidence_asc';

export type BatchActionType = 'approve' | 'hold' | 'reject';

export interface Manufacturer {
  id: number;
  code: string;
  english_name: string;
  korean_name: string;
  is_domestic: boolean;
  created_at: string;
}

export interface VehicleModel {
  id: number;
  code: string;
  manufacturer_id: number;
  manufacturer_code: string;
  english_name: string;
  korean_name: string;
  created_at: string;
}

export type YoloBbox = [number, number, number, number];

export interface YoloDetection {
  bbox: YoloBbox;
  confidence?: number;
  class_name?: string;
  area?: number;
  [k: string]: unknown;
}

export interface RawVisionResult {
  manufacturer_code?: string | null;
  model_code?: string | null;
  visual_evidence?: string | null;
  confidence?: number | null;
  raw_response?: string | null;
  original_image?: string | null;
  bbox?: YoloBbox | null;
  [k: string]: unknown;
}

export interface AnalyzedVehicle {
  id: number;
  image_path: string | null;
  original_image_path: string | null;
  raw_result: RawVisionResult | null;
  manufacturer: string | null;
  model: string | null;
  year: string | null;
  matched_manufacturer_id: number | null;
  matched_model_id: number | null;
  confidence_score: number | null;
  is_verified: boolean;
  review_status: ReviewStatus;
  review_reason: string | null;
  verified_by: string | null;
  verified_at: string | null;
  notes: string | null;
  processing_stage: string | null;
  yolo_detections: YoloDetection[] | null;
  selected_bbox: YoloBbox | null;
  source: string;
  client_uuid: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AnalyzedVehicleListResponse {
  total: number;
  items: AnalyzedVehicle[];
}

export interface VehicleCounts {
  all: number;
  uploaded: number;
  yolo_failed: number;
  yolo_detected: number;
  analysis_complete: number;
  verified: number;
  pending: number;
  on_hold: number;
  approved: number;
  rejected: number;
  avg_confidence: number | null;
  high_confidence: number;
  mid_confidence: number;
  low_confidence: number;
}

export interface FinetuneMode {
  identifier_mode: 'efficientnet' | 'vlm_only' | string;
}

export interface FinetuneStatsEntry {
  manufacturer_id: number;
  korean_name: string;
  english_name: string;
  count: number;
}

export interface FinetuneModelStatsEntry {
  model_id: number;
  korean_name: string;
  english_name: string;
  manufacturer_korean: string;
  count: number;
}

export interface FinetuneStats {
  total: number;
  num_classes: number;
  manufacturers_count: number;
  by_manufacturer: FinetuneStatsEntry[];
  by_model: FinetuneModelStatsEntry[];
}

export interface HwProfile {
  hw?: string;
  backend?: string;
  label?: string;
  preset?: {
    batch_size?: number;
    gradient_accumulation?: number;
    num_workers?: number;
    use_ema?: boolean;
    use_mixup?: boolean;
    [k: string]: unknown;
  };
  [k: string]: unknown;
}

export interface FreezeEpochsInfo {
  freeze_epochs: number;
  reason: string;
  db_classes: number;
  model_classes: number | null;
}

export interface EfficientNetExportResult {
  message: string;
  export_dir: string;
  num_classes: number;
  counts: {
    total_records: number;
    train_count: number;
    val_count: number;
    train_chunks: number;
    val_chunks: number;
    split_ratio: number;
  };
}

export interface EfficientNetTrainConfig {
  learning_rate: number;
  num_epochs: number;
  batch_size: number;
  freeze_epochs: number;
  max_per_class?: number | null;
  min_per_class?: number | null;
  gradient_accumulation: number;
  use_ema: boolean;
  use_mixup: boolean;
  num_workers: number;
  early_stopping_patience: number;
}

export interface TrainStatus {
  status: 'idle' | 'running' | 'done' | 'failed' | 'stopping' | string;
  current_steps?: number;
  total_steps?: number;
  epoch?: number;
  loss?: number;
  val_acc?: number;
  [k: string]: unknown;
}

export interface LogEntry {
  step?: number;
  epoch?: number;
  loss?: number;
  val_acc?: number;
  [k: string]: unknown;
}

export interface TrainLogs {
  logs: LogEntry[];
}

export interface RawLog {
  lines: string[];
}

export interface EvaluateResult {
  accuracy: number;
  avg_confidence: number;
  total: number;
  evaluated: number;
  correct: number;
  incorrect_count: number;
  incorrect_samples: unknown[];
}

// ─── Train Runs (대시보드) ───────────────────────────────────────────────

export interface TrainRunParams {
  learning_rate?: number;
  num_epochs?: number;
  batch_size?: number;
  freeze_epochs?: number;
  max_per_class?: number | null;
  min_per_class?: number | null;
  gradient_accumulation?: number;
  use_ema?: boolean;
  use_mixup?: boolean;
  num_workers?: number | null;
  early_stopping_patience?: number;
}

export interface TrainRunEnv {
  device?: string;
  device_name?: string | null;
  vram_gb?: number | null;
  sm?: string | null;
  precision?: string;
  torch_version?: string;
}

export interface TrainRunData {
  num_classes?: number;
  train_count?: number;
  val_count?: number;
  total_records?: number;
  train_chunks?: number;
  val_chunks?: number;
  split_ratio?: number;
}

export interface TrainRunResult {
  best_val_acc?: number;
  best_epoch?: number;
  last_epoch?: number;
  total_epochs?: number;
  early_stopped?: boolean;
  elapsed_sec?: number;
}

export type TrainRunStatus =
  | "starting"
  | "running"
  | "completed"
  | "early_stopped"
  | "stopped"
  | "failed"
  | string;

export interface TrainRunSummary {
  run_id: string;
  started_at?: string;
  ended_at?: string | null;
  status?: TrainRunStatus;
  params?: TrainRunParams;
  env?: TrainRunEnv | null;
  data?: TrainRunData | null;
  result?: TrainRunResult | null;
}

export interface TrainRunsList {
  runs: TrainRunSummary[];
  count: number;
}

export interface TrainRunDetail {
  run_id: string;
  meta: TrainRunSummary;
  logs: LogEntry[];
  class_mapping: {
    num_classes: number;
    classes: Record<string, {
      manufacturer_id?: number;
      model_id?: number;
      manufacturer_korean?: string;
      manufacturer_english?: string;
      model_korean?: string;
      model_english?: string;
    }>;
  } | null;
}

export interface TrainRunClassHistory {
  run_id: string;
  num_classes: number | null;
  epochs: number[];
  class_acc: Record<string, (number | null)[]>;
  class_meta: Record<string, {
    manufacturer_korean?: string;
    model_korean?: string;
  } | null>;
}

export function listTrainRuns(): Promise<TrainRunsList> {
  return apiRequest<TrainRunsList>("/finetune/train/runs");
}

export function getTrainRun(runId: string): Promise<TrainRunDetail> {
  return apiRequest<TrainRunDetail>(`/finetune/train/runs/${encodeURIComponent(runId)}`);
}

export function getTrainRunClassHistory(runId: string): Promise<TrainRunClassHistory> {
  return apiRequest<TrainRunClassHistory>(`/finetune/train/runs/${encodeURIComponent(runId)}/class-history`);
}

export function deleteTrainRun(runId: string): Promise<{ status: string; run_id: string }> {
  return apiRequest<{ status: string; run_id: string }>(
    `/finetune/train/runs/${encodeURIComponent(runId)}`,
    { method: "DELETE" },
  );
}

// ─── Manufacturers ─────────────────────────────────────────────────────────

export function getManufacturers(params?: {
  isDomestic?: boolean;
  status?: StatusFilter;
  review_status?: ReviewStatus;
}): Promise<Manufacturer[]> {
  return apiRequest<Manufacturer[]>('/admin/manufacturers', {
    query: { is_domestic: params?.isDomestic, status: params?.status, review_status: params?.review_status, limit: 1000 },
  });
}

export interface ManufacturerCreate {
  code: string;
  english_name: string;
  korean_name: string;
  is_domestic: boolean;
}

export function createManufacturer(data: ManufacturerCreate): Promise<Manufacturer> {
  return apiRequest<Manufacturer>('/admin/manufacturers', { method: 'POST', body: data });
}

// ─── Vehicle Models ────────────────────────────────────────────────────────

export function getVehicleModels(params?: {
  manufacturerId?: number;
  status?: StatusFilter;
  review_status?: ReviewStatus;
}): Promise<VehicleModel[]> {
  return apiRequest<VehicleModel[]>('/admin/vehicle-models', {
    query: { manufacturer_id: params?.manufacturerId, status: params?.status, review_status: params?.review_status, limit: 1000 },
  });
}

export interface VehicleModelCreate {
  code: string;
  manufacturer_id: number;
  manufacturer_code: string;
  english_name: string;
  korean_name: string;
}

export function createVehicleModel(data: VehicleModelCreate): Promise<VehicleModel> {
  return apiRequest<VehicleModel>('/admin/vehicle-models', { method: 'POST', body: data });
}

// ─── Analyzed Vehicles ─────────────────────────────────────────────────────

export interface GetAnalyzedVehiclesArgs {
  skip?: number;
  limit?: number;
  status?: StatusFilter;
  review_status?: ReviewStatus;
  manufacturer_id?: number;
  model_id?: number;
  min_confidence?: number;
  max_confidence?: number;
  sort?: ReviewSort;
}

export function getAnalyzedVehicles(args: GetAnalyzedVehiclesArgs = {}): Promise<AnalyzedVehicleListResponse> {
  return apiRequest<AnalyzedVehicleListResponse>('/admin/analyzed-vehicles', {
    query: {
      skip: args.skip,
      limit: args.limit,
      status: args.status === 'all' ? undefined : args.status,
      review_status: args.review_status,
      manufacturer_id: args.manufacturer_id,
      model_id: args.model_id,
      min_confidence: args.min_confidence,
      max_confidence: args.max_confidence,
      sort: args.sort,
    },
  });
}

export function getVehicleCounts(): Promise<VehicleCounts> {
  return apiRequest<VehicleCounts>('/admin/analyzed-vehicles-counts');
}

export function deleteAnalyzedVehicle(id: number): Promise<{ message: string }> {
  return apiRequest<{ message: string }>(`/admin/review/${id}`, { method: 'DELETE' });
}

export interface DeleteAllUnverifiedResponse {
  message: string;
  total: number;
  deleted_files: number;
  failed_files: number;
}

export function deleteAllUnverified(): Promise<DeleteAllUnverifiedResponse> {
  return apiRequest<DeleteAllUnverifiedResponse>('/admin/review-delete-all', { method: 'DELETE' });
}

export interface UpdateAnalyzedVehicleBody {
  matched_manufacturer_id: number;
  matched_model_id: number;
  manufacturer?: string;
  model?: string;
}

export function updateAnalyzedVehicle(
  id: number,
  body: UpdateAnalyzedVehicleBody,
): Promise<ReviewActionResponse> {
  return apiRequest<ReviewActionResponse>(`/admin/review/${id}`, {
    method: 'PATCH',
    body,
  });
}

export interface ReviewActionResponse {
  message: string;
  data: AnalyzedVehicle;
  training_synced?: boolean;
  training_removed?: boolean;
}

export function saveToTraining(id: number): Promise<ReviewActionResponse> {
  return apiRequest<ReviewActionResponse>(`/admin/review/${id}`, {
    method: 'POST',
  });
}

export function holdAnalyzedVehicle(id: number, reason?: string): Promise<ReviewActionResponse> {
  return apiRequest<ReviewActionResponse>(`/admin/review/${id}/hold`, {
    method: 'POST',
    body: { reason: reason ?? null },
  });
}

export function rejectAnalyzedVehicle(id: number, reason?: string): Promise<ReviewActionResponse> {
  return apiRequest<ReviewActionResponse>(`/admin/review/${id}/reject`, {
    method: 'POST',
    body: { reason: reason ?? null },
  });
}

export function reopenAnalyzedVehicle(id: number): Promise<ReviewActionResponse> {
  return apiRequest<ReviewActionResponse>(`/admin/review/${id}/reopen`, {
    method: 'POST',
  });
}

export function reanalyzeVehicle(id: number): Promise<{ message: string; data: AnalyzedVehicle }> {
  return apiRequest<{ message: string; data: AnalyzedVehicle }>(`/admin/analyze/${id}`, {
    method: 'POST',
  });
}

export interface BatchActionStartEvent {
  type: 'start';
  total: number;
  action: BatchActionType;
}

export interface BatchActionProgressEvent {
  type: 'progress';
  current: number;
  total: number;
  succeeded: number;
  failed: number;
  item_id: number;
  reason?: string;
}

export interface BatchActionDoneEvent {
  type: 'done';
  total: number;
  succeeded: number;
  failed: number;
  failed_ids: number[];
}

export type BatchActionEvent = BatchActionStartEvent | BatchActionProgressEvent | BatchActionDoneEvent;

export async function streamBatchAction(
  payload: { action: BatchActionType; ids: number[]; reason?: string },
  onEvent: (event: BatchActionEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch('/admin/review/batch-action', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      action: payload.action,
      ids: payload.ids,
      reason: payload.reason ?? null,
    }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`batch-action 요청 실패: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data:')) continue;
      const data = trimmed.slice(5).trim();
      if (!data) continue;
      try {
        onEvent(JSON.parse(data) as BatchActionEvent);
      } catch (err) {
        console.error('batch-action SSE parse error', err, data);
      }
    }
  }
}

// ─── Finetune ──────────────────────────────────────────────────────────────

export function getFinetuneMode(): Promise<FinetuneMode> {
  return apiRequest<FinetuneMode>('/finetune/mode');
}

export function getFinetuneStats(): Promise<FinetuneStats> {
  return apiRequest<FinetuneStats>('/finetune/stats');
}

export function getHwProfile(): Promise<HwProfile> {
  return apiRequest<HwProfile>('/finetune/hw-profile');
}

export function getFreezeEpochsInfo(minPerClass?: number): Promise<FreezeEpochsInfo> {
  return apiRequest<FreezeEpochsInfo>('/finetune/freeze-epochs', {
    query: { min_per_class: minPerClass },
  });
}

export interface EfficientNetExportArgs {
  manufacturer_id?: number;
  date_from?: string;
  date_to?: string;
  split?: number;
  max_per_class?: number | null;
  min_per_class?: number | null;
}

export function exportEfficientNet(args: EfficientNetExportArgs = {}): Promise<EfficientNetExportResult> {
  return apiRequest<EfficientNetExportResult>('/finetune/export-efficientnet', {
    method: 'POST',
    body: { split: 0.9, ...args },
  });
}

export function startTraining(config: EfficientNetTrainConfig): Promise<unknown> {
  return apiRequest<unknown>('/finetune/train/start', { method: 'POST', body: config });
}

export function stopTraining(): Promise<unknown> {
  return apiRequest<unknown>('/finetune/train/stop', { method: 'POST' });
}

export function getTrainStatus(): Promise<TrainStatus> {
  return apiRequest<TrainStatus>('/finetune/train/status');
}

export function getTrainLogs(tail = 100): Promise<TrainLogs> {
  return apiRequest<TrainLogs>('/finetune/train/logs', { query: { tail } });
}

export function getRawLog(tail = 100): Promise<RawLog> {
  return apiRequest<RawLog>('/finetune/train/raw-log', { query: { tail } });
}

export function evaluateModel(sampleSize = 50): Promise<EvaluateResult> {
  return apiRequest<EvaluateResult>('/finetune/evaluate', { query: { sample_size: sampleSize } });
}

// ─── Error helper ──────────────────────────────────────────────────────────

export function extractErrorMessage(err: unknown): string {
  if (err instanceof ApiError) {
    const body = err.body as { detail?: unknown } | string | null;
    if (body && typeof body === 'object' && 'detail' in body) {
      const { detail } = body;
      if (typeof detail === 'string' && detail.trim()) return detail;
    }
    if (typeof body === 'string' && body.trim()) return body;
    return `HTTP ${err.status}`;
  }
  if (err instanceof Error) return err.message;
  return String(err);
}
