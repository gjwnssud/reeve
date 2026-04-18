import { useState } from "react";

import { TopNav, type TabKey } from "./components/TopNav";
import { BatchTab } from "./pages/BatchTab";
import { SingleTab } from "./pages/SingleTab";

export default function App() {
  const [tab, setTab] = useState<TabKey>("single");
  return (
    <div className="min-h-screen bg-background text-foreground">
      <TopNav value={tab} onChange={setTab} />
      <main className="mx-auto max-w-5xl px-4 py-6">
        {tab === "single" ? <SingleTab /> : <BatchTab />}
      </main>
      <footer className="py-6 text-center text-xs text-muted-foreground">
        Reeve Vehicle Identification Service
      </footer>
    </div>
  );
}
