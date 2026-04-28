import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import {
  Button, Badge, Input, Label, Skeleton,
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from "@reeve/ui";
import { Plus } from "lucide-react";

import { getManufacturers, createManufacturer, extractErrorMessage, type Manufacturer } from "../../lib/api";

type DomesticFilter = "all" | "domestic" | "foreign";

const schema = z.object({
  code: z.string().min(1, "코드를 입력하세요").toUpperCase(),
  english_name: z.string().min(1, "영문명을 입력하세요"),
  korean_name: z.string().min(1, "한글명을 입력하세요"),
  is_domestic: z.boolean(),
});
type FormData = z.infer<typeof schema>;

export function ManufacturersTab() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<DomesticFilter>("all");
  const [open, setOpen] = useState(false);

  const is_domestic = filter === "all" ? undefined : filter === "domestic";
  const { data, isLoading } = useQuery({
    queryKey: ["manufacturers", filter],
    queryFn: () => getManufacturers({ isDomestic: is_domestic }),
  });

  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { code: "", english_name: "", korean_name: "", is_domestic: false },
  });

  const { mutateAsync } = useMutation({
    mutationFn: createManufacturer,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["manufacturers"] });
    },
  });

  const onSubmit = async (values: FormData) => {
    try {
      await mutateAsync(values);
      toast.success("제조사가 추가되었습니다");
      setOpen(false);
      reset();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1 h-4 w-4" /> 제조사 추가
        </Button>
        <div className="flex rounded-md border text-sm">
          {(["all", "domestic", "foreign"] as DomesticFilter[]).map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setFilter(v)}
              className={`px-3 py-1.5 transition first:rounded-l-md last:rounded-r-md ${
                filter === v ? "bg-primary text-primary-foreground" : "hover:bg-muted"
              }`}
            >
              {v === "all" ? "전체" : v === "domestic" ? "국내" : "해외"}
            </button>
          ))}
        </div>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              {["ID", "코드", "영문명", "한글명", "구분", "등록일"].map((h) => (
                <th key={h} className="px-4 py-3 text-left font-medium text-muted-foreground">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="border-b">
                  {Array.from({ length: 6 }).map((__, j) => (
                    <td key={j} className="px-4 py-3"><Skeleton className="h-4 w-full" /></td>
                  ))}
                </tr>
              ))
            ) : data?.length === 0 ? (
              <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">데이터 없음</td></tr>
            ) : (
              data?.map((m: Manufacturer) => (
                <tr key={m.id} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 text-muted-foreground">{m.id}</td>
                  <td className="px-4 py-3 font-mono font-medium">{m.code}</td>
                  <td className="px-4 py-3">{m.english_name}</td>
                  <td className="px-4 py-3">{m.korean_name}</td>
                  <td className="px-4 py-3">
                    <Badge variant={m.is_domestic ? "default" : "secondary"}>
                      {m.is_domestic ? "국내" : "해외"}
                    </Badge>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(m.created_at).toLocaleDateString("ko-KR")}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <Dialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) reset(); }}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>제조사 추가</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="mf-code">코드 *</Label>
              <Input id="mf-code" placeholder="예: HYUNDAI" {...register("code")} />
              {errors.code && <p className="text-xs text-destructive">{errors.code.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mf-en">영문명 *</Label>
              <Input id="mf-en" placeholder="예: Hyundai Motor Company" {...register("english_name")} />
              {errors.english_name && <p className="text-xs text-destructive">{errors.english_name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="mf-ko">한글명 *</Label>
              <Input id="mf-ko" placeholder="예: 현대자동차" {...register("korean_name")} />
              {errors.korean_name && <p className="text-xs text-destructive">{errors.korean_name.message}</p>}
            </div>
            <div className="flex items-center gap-2">
              <input type="checkbox" id="mf-domestic" className="h-4 w-4 rounded border-input accent-primary" {...register("is_domestic")} />
              <Label htmlFor="mf-domestic" className="cursor-pointer">국내 제조사</Label>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={() => { setOpen(false); reset(); }}>취소</Button>
              <Button type="submit" disabled={isSubmitting}>저장</Button>
            </div>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
