import { ApiError, apiRequest } from '@reeve/shared';

// ─── Types ─────────────────────────────────────────────────────────────────

export type StatusFilter = 'all' | 'uploaded' | 'yolo_failed' | 'yolo_detected' | 'analysis_complete' | 'verified';

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

export interface AnalyzedVehicle {
  id: number;
  image_path: string | null;
  original_image_path: string | null;
  raw_result: unknown;
  manufacturer: string | null;
  model: string | null;
  year: string | null;
  matched_manufacturer_id: number | null;
  matched_model_id: number | null;
  confidence_score: number | null;
  is_verified: boolean;
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

// ─── Manufacturers ─────────────────────────────────────────────────────────

export function getManufacturers(isDomestic?: boolean): Promise<Manufacturer[]> {
  return apiRequest<Manufacturer[]>('/admin/manufacturers', {
    query: { is_domestic: isDomestic, limit: 1000 },
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

export function getVehicleModels(manufacturerId?: number): Promise<VehicleModel[]> {
  return apiRequest<VehicleModel[]>('/admin/vehicle-models', {
    query: { manufacturer_id: manufacturerId, limit: 1000 },
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
  manufacturer_id?: number;
  model_id?: number;
}

export function getAnalyzedVehicles(args: GetAnalyzedVehiclesArgs = {}): Promise<AnalyzedVehicleListResponse> {
  return apiRequest<AnalyzedVehicleListResponse>('/admin/analyzed-vehicles', {
    query: {
      skip: args.skip,
      limit: args.limit,
      status: args.status === 'all' ? undefined : args.status,
      manufacturer_id: args.manufacturer_id,
      model_id: args.model_id,
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
): Promise<{ message: string; data: AnalyzedVehicle }> {
  return apiRequest<{ message: string; data: AnalyzedVehicle }>(`/admin/review/${id}`, {
    method: 'PATCH',
    body,
  });
}

export function saveToTraining(id: number): Promise<{ message: string; data: AnalyzedVehicle }> {
  return apiRequest<{ message: string; data: AnalyzedVehicle }>(`/admin/review/${id}`, {
    method: 'POST',
  });
}

export function reanalyzeVehicle(id: number): Promise<{ message: string; data: AnalyzedVehicle }> {
  return apiRequest<{ message: string; data: AnalyzedVehicle }>(`/admin/analyze/${id}`, {
    method: 'POST',
  });
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

export function getFreezeEpochsInfo(): Promise<FreezeEpochsInfo> {
  return apiRequest<FreezeEpochsInfo>('/finetune/freeze-epochs');
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
