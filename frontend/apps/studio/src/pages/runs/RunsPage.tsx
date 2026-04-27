import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button, Badge, Skeleton } from "@reeve/ui";
import { RefreshCw } from "lucide-react";
import { listTrainRuns, deleteTrainRun, extractErrorMessage } from "../../lib/api";
import { RunListTable } from "./RunListTable";
import { RunDetailView } from "./RunDetailView";
import { RunCompareView } from "./RunCompareView";
import { ClassTrackingView } from "./ClassTrackingView";

type Tab = "detail" | "compare" | "classes";

export function RunsPage() {
  const qc = useQueryClient();
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("detail");
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["train-runs"],
    queryFn: listTrainRuns,
    refetchInterval: 5000, // 학습 중일 때 자동 갱신
  });

  const runs = useMemo(() => data?.runs ?? [], [data]);

  // 첫 로드 시 가장 최근 run 자동 선택
  useEffect(() => {
    if (selectedIds.length === 0 && runs.length > 0 && runs[0]) {
      setSelectedIds([runs[0].run_id]);
    }
  }, [runs, selectedIds.length]);

  const { mutateAsync: doDelete } = useMutation({
    mutationFn: (runId: string) => {
      setDeletingId(runId);
      return deleteTrainRun(runId);
    },
    onSuccess: (_, runId) => {
      toast.success(`run ${runId} 삭제됨`);
      setSelectedIds((prev) => prev.filter((id) => id !== runId));
      qc.invalidateQueries({ queryKey: ["train-runs"] });
    },
    onError: (e) => toast.error(extractErrorMessage(e)),
    onSettled: () => setDeletingId(null),
  });

  const handleToggle = (runId: string) => {
    setSelectedIds((prev) =>
      prev.includes(runId) ? prev.filter((id) => id !== runId) : [...prev, runId],
    );
  };

  const handleClickRow = (runId: string) => {
    setSelectedIds([runId]);
    setTab("detail");
  };

  const completedSelected = useMemo(
    () => selectedIds.filter((id) => runs.find((r) => r.run_id === id)?.status !== "running" && runs.find((r) => r.run_id === id)?.status !== "starting"),
    [selectedIds, runs],
  );

  const tabBtn = (key: Tab, label: string, disabled = false) => (
    <button
      type="button"
      disabled={disabled}
      onClick={() => setTab(key)}
      className={`px-3 py-1.5 text-sm border-b-2 ${
        tab === key
          ? "border-primary font-semibold"
          : "border-transparent text-muted-foreground hover:text-foreground"
      } disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {label}
    </button>
  );

  return (
    <div className="mx-auto max-w-7xl space-y-4 p-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">학습 이력</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            매 학습마다 자동 저장된 run을 비교/분석합니다. 행을 클릭하면 상세, 체크박스로 다중 선택 시 비교/클래스 추적 탭이 활성화됩니다.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline">{runs.length} runs</Badge>
          <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`mr-1 h-4 w-4 ${isFetching ? "animate-spin" : ""}`} />
            새로고침
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <RunListTable
          runs={runs}
          selectedIds={selectedIds}
          onToggle={handleToggle}
          onDelete={(id) => void doDelete(id)}
          onClickRow={handleClickRow}
          isDeleting={deletingId}
        />
      )}

      {/* 탭 + 뷰 영역 */}
      {selectedIds.length > 0 && (
        <div className="rounded-lg border">
          <div className="flex items-center gap-1 border-b px-2">
            {tabBtn("detail", `상세 (${selectedIds.length === 1 ? selectedIds[0] : `${selectedIds.length}개 선택`})`)}
            {tabBtn("compare", "회차 비교", selectedIds.length < 2)}
            {tabBtn("classes", "클래스 추적", completedSelected.length === 0)}
          </div>
          <div className="p-4">
            {tab === "detail" && selectedIds.length >= 1 && (
              <RunDetailView runId={selectedIds[0]!} />
            )}
            {tab === "compare" && selectedIds.length >= 2 && (
              <RunCompareView runIds={selectedIds} />
            )}
            {tab === "classes" && completedSelected.length > 0 && (
              <ClassTrackingView runIds={completedSelected} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}
