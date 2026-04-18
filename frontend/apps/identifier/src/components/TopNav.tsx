import { useThemeContext } from "@reeve/shared";
import { Button, Tabs, TabsList, TabsTrigger } from "@reeve/ui";
import { Car, FolderOpen, ImageIcon, Moon, Sun } from "lucide-react";

export type TabKey = "single" | "batch";

export function TopNav({
  value,
  onChange,
}: {
  value: TabKey;
  onChange: (v: TabKey) => void;
}) {
  const { theme, toggle } = useThemeContext();

  return (
    <header className="sticky top-0 z-10 border-b bg-brand-gradient text-white">
      <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
        <div className="flex items-center gap-2 font-semibold">
          <Car className="h-5 w-5" />
          <span>Reeve Identifier</span>
        </div>
        <div className="flex items-center gap-3">
          <Tabs value={value} onValueChange={(v) => onChange(v as TabKey)}>
            <TabsList className="bg-white/15 text-white">
              <TabsTrigger
                value="single"
                className="data-[state=active]:bg-white data-[state=active]:text-slate-900"
              >
                <ImageIcon className="mr-1 h-4 w-4" /> 단건 판별
              </TabsTrigger>
              <TabsTrigger
                value="batch"
                className="data-[state=active]:bg-white data-[state=active]:text-slate-900"
              >
                <FolderOpen className="mr-1 h-4 w-4" /> 폴더 배치
              </TabsTrigger>
            </TabsList>
          </Tabs>
          <Button
            size="icon"
            variant="ghost"
            className="text-white hover:bg-white/15 hover:text-white"
            onClick={toggle}
            aria-label="테마 전환"
          >
            {theme === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </header>
  );
}
