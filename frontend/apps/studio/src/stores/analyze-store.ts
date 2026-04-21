import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import { STORAGE_KEYS } from "@reeve/shared";
import type { Detection, AnalyzeSSEEvent } from "../lib/analyzeApi";

export type ImageStatus = "queued" | "uploading" | "detecting" | "analyzing" | "done" | "failed";
export type ImageSource = "file" | "folder" | "server";

export interface AnalysisResult {
  id: number;
  manufacturer: string | null;
  model: string | null;
  year: string | null;
  confidence_score: number;
  matched_manufacturer_id: number | null;
  matched_model_id: number | null;
}

export interface ImageState {
  id: string;
  source: ImageSource;
  file: File;
  preview: string;
  status: ImageStatus;
  analyzedId?: number;
  originalImagePath?: string;
  detections?: Detection[];
  selectedBbox?: [number, number, number, number];
  result?: AnalysisResult;
  progress?: number;
  progressMsg?: string;
  error?: string;
}

export interface Stats {
  total: number;
  detected: number;
  detectionFailed: number;
  analyzed: number;
  analysisError: number;
}

interface AnalyzeStore {
  images: Record<string, ImageState>;
  fileStats: Stats;
  folderStats: Stats;
  serverStats: Stats;
  folderWatchRunning: boolean;

  addImage: (img: ImageState) => void;
  setFolderWatchRunning: (v: boolean) => void;
  updateImage: (id: string, patch: Partial<ImageState>) => void;
  removeImage: (id: string) => void;
  clearImages: (source: ImageSource) => void;
  applySSEEvent: (id: string, ev: AnalyzeSSEEvent) => void;
  incrementStat: (source: ImageSource, key: keyof Stats, delta?: number) => void;
  resetStats: (source: ImageSource) => void;
}

const emptyStats = (): Stats => ({
  total: 0, detected: 0, detectionFailed: 0, analyzed: 0, analysisError: 0,
});

// Stats are persisted per clientUUID. We defer the actual key to runtime.
// We use a shared persist store that reads uuid from localStorage.
function getUUID(): string {
  return localStorage.getItem(STORAGE_KEYS.clientUUID) ?? "default";
}

export const useAnalyzeStore = create<AnalyzeStore>()(
  (set) => ({
    images: {},
    folderWatchRunning: false,
    fileStats: (() => {
      try {
        const uuid = getUUID();
        const saved = localStorage.getItem(STORAGE_KEYS.fileStats(uuid));
        return saved ? (JSON.parse(saved) as Stats) : emptyStats();
      } catch { return emptyStats(); }
    })(),
    folderStats: (() => {
      try {
        const uuid = getUUID();
        const saved = localStorage.getItem(STORAGE_KEYS.folderStats(uuid));
        return saved ? (JSON.parse(saved) as Stats) : emptyStats();
      } catch { return emptyStats(); }
    })(),
    serverStats: (() => {
      try {
        const uuid = getUUID();
        const saved = localStorage.getItem(STORAGE_KEYS.serverStats(uuid));
        return saved ? (JSON.parse(saved) as Stats) : emptyStats();
      } catch { return emptyStats(); }
    })(),

    setFolderWatchRunning: (v) => set({ folderWatchRunning: v }),

    addImage: (img) =>
      set((s) => ({ images: { ...s.images, [img.id]: img } })),

    updateImage: (id, patch) =>
      set((s) => {
        const existing = s.images[id];
        if (!existing) return s;
        return { images: { ...s.images, [id]: { ...existing, ...patch } } };
      }),

    removeImage: (id) =>
      set((s) => {
        const { [id]: removed, ...rest } = s.images;
        if (removed?.preview) URL.revokeObjectURL(removed.preview);
        return { images: rest };
      }),

    clearImages: (source) =>
      set((s) => {
        const next: Record<string, ImageState> = {};
        for (const [k, v] of Object.entries(s.images)) {
          if (v.source === source) {
            if (v.preview) URL.revokeObjectURL(v.preview);
          } else {
            next[k] = v;
          }
        }
        return { images: next };
      }),

    applySSEEvent: (id, ev) =>
      set((s) => {
        const img = s.images[id];
        if (!img) return s;
        if (ev.event === "progress") {
          return { images: { ...s.images, [id]: { ...img, status: "analyzing", progress: ev.progress, progressMsg: ev.message } } };
        }
        if (ev.event === "completed" && ev.result) {
          return { images: { ...s.images, [id]: { ...img, status: "done", result: ev.result, progress: 100, progressMsg: undefined } } };
        }
        if (ev.event === "error") {
          return { images: { ...s.images, [id]: { ...img, status: "failed", error: ev.message } } };
        }
        return s;
      }),

    incrementStat: (source, key, delta = 1) =>
      set((s) => {
        const field = source === "file" ? "fileStats" : source === "folder" ? "folderStats" : "serverStats";
        const next = { ...s[field], [key]: s[field][key] + delta };
        try {
          const uuid = getUUID();
          const storageKey = source === "file" ? STORAGE_KEYS.fileStats(uuid) : source === "folder" ? STORAGE_KEYS.folderStats(uuid) : STORAGE_KEYS.serverStats(uuid);
          localStorage.setItem(storageKey, JSON.stringify(next));
        } catch {}
        return { [field]: next };
      }),

    resetStats: (source) =>
      set(() => {
        const field = source === "file" ? "fileStats" : source === "folder" ? "folderStats" : "serverStats";
        try {
          const uuid = getUUID();
          const storageKey = source === "file" ? STORAGE_KEYS.fileStats(uuid) : source === "folder" ? STORAGE_KEYS.folderStats(uuid) : STORAGE_KEYS.serverStats(uuid);
          localStorage.removeItem(storageKey);
        } catch {}
        return { [field]: emptyStats() };
      }),
  })
);
