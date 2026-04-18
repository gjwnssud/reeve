export type Bbox = [number, number, number, number];

export type VehicleDetection = {
  index: number;
  bbox: number[];
  confidence: number;
  class_name: string;
  area: number;
};

export type DetectionResult = {
  detections: VehicleDetection[];
  count: number;
  image_width: number;
  image_height: number;
};

export type TopKDetail = {
  rank: number;
  manufacturer_id: number;
  model_id: number;
  similarity: number;
  image_path?: string | null;
};

export type IdentificationStatus = 'identified' | 'low_confidence' | 'no_match';

export type IdentificationResult = {
  status: IdentificationStatus | string;
  manufacturer_korean?: string | null;
  manufacturer_english?: string | null;
  model_korean?: string | null;
  model_english?: string | null;
  confidence: number;
  message: string;
  detection?: VehicleDetection | null;
  image_width: number;
  image_height: number;
  top_k_details: TopKDetail[];
};
