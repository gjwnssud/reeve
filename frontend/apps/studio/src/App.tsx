import { Routes, Route, Navigate } from "react-router-dom";
import { StudioLayout } from "./layouts/StudioLayout";
import { BasicDataPage } from "./pages/basic-data/BasicDataPage";
import { AdminPage } from "./pages/admin/AdminPage";
import { FinetunePage } from "./pages/finetune/FinetunePage";
import { AnalyzePage } from "./pages/analyze/AnalyzePage";

export default function App() {
  return (
    <Routes>
      <Route element={<StudioLayout />}>
        <Route path="/" element={<Navigate to="/basic-data" replace />} />
        <Route path="/basic-data" element={<BasicDataPage />} />
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/finetune" element={<FinetunePage />} />
        <Route path="/analyze" element={<AnalyzePage />} />
        <Route path="*" element={<Navigate to="/basic-data" replace />} />
      </Route>
    </Routes>
  );
}
