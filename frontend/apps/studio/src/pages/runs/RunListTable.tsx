import { useMemo } from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
} from "@tanstack/react-table";
import { Trash2 } from "lucide-react";
import { Badge, Button, cn } from "@reeve/ui";
import type { TrainRunSummary } from "../../lib/api";

interface Props {
  runs: TrainRunSummary[];
  selectedIds: string[];
  onToggle: (runId: string) => void;
  onDelete: (runId: string) => void;
  onClickRow?: (runId: string) => void;
  isDeleting?: string | null;
}

function formatDuration(sec?: number) {
  if (sec == null) return "-";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}

function statusVariant(status?: string): "default" | "secondary" | "destructive" | "outline" {
  if (status === "completed") return "default";
  if (status === "early_stopped") return "default";
  if (status === "running" || status === "starting") return "secondary";
  if (status === "failed") return "destructive";
  return "outline";
}

function statusLabel(status?: string) {
  switch (status) {
    case "completed": return "완료";
    case "early_stopped": return "조기 종료";
    case "running": return "실행 중";
    case "starting": return "시작 중";
    case "stopped": return "중지됨";
    case "failed": return "실패";
    default: return status ?? "-";
  }
}

export function RunListTable({ runs, selectedIds, onToggle, onDelete, onClickRow, isDeleting }: Props) {
  const columns = useMemo<ColumnDef<TrainRunSummary>[]>(() => [
    {
      id: "select",
      header: () => null,
      cell: ({ row }) => (
        <input
          type="checkbox"
          className="h-4 w-4 accent-primary"
          checked={selectedIds.includes(row.original.run_id)}
          onChange={() => onToggle(row.original.run_id)}
          onClick={(e) => e.stopPropagation()}
        />
      ),
      size: 32,
    },
    {
      header: "Run ID",
      accessorKey: "run_id",
      cell: ({ row }) => <span className="font-mono text-xs">{row.original.run_id}</span>,
    },
    {
      header: "시작 시각",
      accessorKey: "started_at",
      cell: ({ row }) => (
        <span className="text-xs text-muted-foreground">
          {row.original.started_at ? row.original.started_at.replace("T", " ") : "-"}
        </span>
      ),
    },
    {
      header: "상태",
      accessorKey: "status",
      cell: ({ row }) => (
        <Badge variant={statusVariant(row.original.status)} className="text-[10px]">
          {statusLabel(row.original.status)}
        </Badge>
      ),
    },
    {
      header: "Best Acc",
      cell: ({ row }) => {
        const acc = row.original.result?.best_val_acc;
        return <span className="font-semibold">{acc != null ? `${acc.toFixed(1)}%` : "-"}</span>;
      },
    },
    {
      header: "Best Ep",
      cell: ({ row }) => row.original.result?.best_epoch ?? "-",
    },
    {
      header: "에폭",
      cell: ({ row }) => {
        const r = row.original.result;
        if (!r) return "-";
        return `${r.last_epoch ?? "-"}/${r.total_epochs ?? "-"}`;
      },
    },
    {
      header: "클래스",
      cell: ({ row }) => row.original.data?.num_classes ?? "-",
    },
    {
      header: "학습/검증",
      cell: ({ row }) => {
        const d = row.original.data;
        if (!d) return "-";
        return <span className="text-xs">{d.train_count?.toLocaleString()}/{d.val_count?.toLocaleString()}</span>;
      },
    },
    {
      header: "MixUp",
      cell: ({ row }) => row.original.params?.use_mixup ? "ON" : "OFF",
    },
    {
      header: "EMA",
      cell: ({ row }) => row.original.params?.use_ema ? "ON" : "OFF",
    },
    {
      header: "min/max",
      cell: ({ row }) => {
        const p = row.original.params;
        if (!p) return "-";
        return <span className="text-xs">{p.min_per_class ?? "-"}/{p.max_per_class ?? "-"}</span>;
      },
    },
    {
      header: "시간",
      cell: ({ row }) => formatDuration(row.original.result?.elapsed_sec),
    },
    {
      id: "actions",
      header: () => null,
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          disabled={isDeleting === row.original.run_id}
          onClick={(e) => {
            e.stopPropagation();
            if (confirm(`run ${row.original.run_id} 을 삭제하시겠습니까?`)) {
              onDelete(row.original.run_id);
            }
          }}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      ),
    },
  ], [selectedIds, onToggle, onDelete, isDeleting]);

  const table = useReactTable({
    data: runs,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="overflow-x-auto rounded-lg border">
      <table className="w-full text-sm">
        <thead className="bg-muted/50">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th key={h.id} className="px-2 py-2 text-left text-xs font-semibold whitespace-nowrap">
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-3 py-6 text-center text-muted-foreground text-sm">
                저장된 학습 이력이 없습니다.
              </td>
            </tr>
          ) : (
            table.getRowModel().rows.map((row) => (
              <tr
                key={row.id}
                className={cn(
                  "border-t cursor-pointer hover:bg-muted/30 transition-colors",
                  selectedIds.includes(row.original.run_id) && "bg-primary/5",
                )}
                onClick={() => onClickRow?.(row.original.run_id)}
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-2 py-2 whitespace-nowrap">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
