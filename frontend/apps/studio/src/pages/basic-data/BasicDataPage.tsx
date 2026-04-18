import { useState } from "react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@reeve/ui";
import { ManufacturersTab } from "./ManufacturersTab";
import { ModelsTab } from "./ModelsTab";

export function BasicDataPage() {
  const [tab, setTab] = useState<"manufacturers" | "models">("manufacturers");

  return (
    <div className="mx-auto max-w-5xl p-6">
      <h1 className="mb-4 text-xl font-semibold">기초데이터 관리</h1>
      <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
        <TabsList className="mb-4">
          <TabsTrigger value="manufacturers">제조사 관리</TabsTrigger>
          <TabsTrigger value="models">차량 모델 관리</TabsTrigger>
        </TabsList>
        <TabsContent value="manufacturers">
          <ManufacturersTab />
        </TabsContent>
        <TabsContent value="models">
          <ModelsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}
