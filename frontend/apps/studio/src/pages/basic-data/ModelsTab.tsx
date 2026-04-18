import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";
import {
  Button, Input, Label, Skeleton,
  Dialog, DialogContent, DialogHeader, DialogTitle,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@reeve/ui";
import { Plus } from "lucide-react";

import {
  getManufacturers, getVehicleModels, createVehicleModel,
  extractErrorMessage, type VehicleModel,
} from "../../lib/api";

const schema = z.object({
  manufacturer_id: z.coerce.number().min(1, "제조사를 선택하세요"),
  manufacturer_code: z.string().min(1),
  code: z.string().min(1, "모델 코드를 입력하세요").toUpperCase(),
  english_name: z.string().min(1, "영문명을 입력하세요"),
  korean_name: z.string().min(1, "한글명을 입력하세요"),
});
type FormData = z.infer<typeof schema>;

export function ModelsTab() {
  const qc = useQueryClient();
  const [filterMfId, setFilterMfId] = useState<number | undefined>(undefined);
  const [open, setOpen] = useState(false);

  const { data: manufacturers } = useQuery({
    queryKey: ["manufacturers"],
    queryFn: () => getManufacturers(),
  });

  const { data, isLoading } = useQuery({
    queryKey: ["vehicle-models", filterMfId],
    queryFn: () => getVehicleModels(filterMfId),
  });

  const { register, handleSubmit, reset, setValue, watch, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { manufacturer_id: 0, manufacturer_code: "", code: "", english_name: "", korean_name: "" },
  });

  const { mutateAsync } = useMutation({
    mutationFn: createVehicleModel,
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["vehicle-models"] });
    },
  });

  const onManufacturerSelect = (val: string) => {
    const id = Number(val);
    const mf = manufacturers?.find((m) => m.id === id);
    setValue("manufacturer_id", id);
    setValue("manufacturer_code", mf?.code ?? "");
  };

  const onSubmit = async (values: FormData) => {
    try {
      await mutateAsync(values);
      toast.success("차량 모델이 추가되었습니다");
      setOpen(false);
      reset();
    } catch (e) {
      toast.error(extractErrorMessage(e));
    }
  };

  const watchedMfId = watch("manufacturer_id");

  const mfMap = Object.fromEntries((manufacturers ?? []).map((m) => [m.id, m]));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button size="sm" onClick={() => setOpen(true)}>
          <Plus className="mr-1 h-4 w-4" /> 모델 추가
        </Button>
        <Select
          value={filterMfId !== undefined ? String(filterMfId) : "all"}
          onValueChange={(v) => setFilterMfId(v === "all" ? undefined : Number(v))}
        >
          <SelectTrigger className="w-48">
            <SelectValue placeholder="전체 제조사" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">전체 제조사</SelectItem>
            {manufacturers?.map((m) => (
              <SelectItem key={m.id} value={String(m.id)}>{m.korean_name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-md border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              {["ID", "코드", "제조사", "영문명", "한글명", "등록일"].map((h) => (
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
              data?.map((m: VehicleModel) => (
                <tr key={m.id} className="border-b hover:bg-muted/30 transition-colors">
                  <td className="px-4 py-3 text-muted-foreground">{m.id}</td>
                  <td className="px-4 py-3 font-mono font-medium">{m.code}</td>
                  <td className="px-4 py-3">{mfMap[m.manufacturer_id]?.korean_name ?? m.manufacturer_code}</td>
                  <td className="px-4 py-3">{m.english_name}</td>
                  <td className="px-4 py-3">{m.korean_name}</td>
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
            <DialogTitle>차량 모델 추가</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <div className="space-y-1.5">
              <Label>제조사 *</Label>
              <Select value={watchedMfId ? String(watchedMfId) : ""} onValueChange={onManufacturerSelect}>
                <SelectTrigger>
                  <SelectValue placeholder="제조사 선택" />
                </SelectTrigger>
                <SelectContent>
                  {manufacturers?.map((m) => (
                    <SelectItem key={m.id} value={String(m.id)}>{m.korean_name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.manufacturer_id && <p className="text-xs text-destructive">{errors.manufacturer_id.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="model-code">모델 코드 *</Label>
              <Input id="model-code" placeholder="예: SONATA" {...register("code")} />
              {errors.code && <p className="text-xs text-destructive">{errors.code.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="model-en">영문명 *</Label>
              <Input id="model-en" placeholder="예: Sonata" {...register("english_name")} />
              {errors.english_name && <p className="text-xs text-destructive">{errors.english_name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="model-ko">한글명 *</Label>
              <Input id="model-ko" placeholder="예: 소나타" {...register("korean_name")} />
              {errors.korean_name && <p className="text-xs text-destructive">{errors.korean_name.message}</p>}
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
