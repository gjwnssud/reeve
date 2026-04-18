import { NavLink, Outlet } from "react-router-dom";
import { Camera, Database, ListChecks, Settings2, Car, Moon, Sun } from "lucide-react";
import { useThemeContext } from "@reeve/shared";
import { Button, cn } from "@reeve/ui";

const navItems = [
  { to: "/analyze", icon: Camera, label: "이미지 분석" },
  { to: "/admin", icon: Database, label: "차량데이터 관리" },
  { to: "/basic-data", icon: ListChecks, label: "기초데이터 관리" },
  { to: "/finetune", icon: Settings2, label: "파인튜닝" },
];

function SidebarContent() {
  const { theme, toggle } = useThemeContext();
  return (
    <div className="flex h-full flex-col" style={{ background: "linear-gradient(180deg,#667eea 0%,#764ba2 100%)" }}>
      <div className="flex items-center justify-center border-b border-white/20 px-4 py-5">
        <a href="/" className="flex items-center gap-2 text-lg font-bold text-white no-underline">
          <Car className="h-5 w-5" />
          Reeve
        </a>
      </div>
      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                isActive
                  ? "bg-white/25 font-semibold text-white"
                  : "text-white/75 hover:bg-white/10 hover:text-white"
              )
            }
          >
            <Icon className="h-4 w-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="border-t border-white/20 p-3">
        <Button
          variant="outline"
          size="sm"
          className="w-full border-white/40 bg-transparent text-white hover:bg-white/15 hover:text-white"
          onClick={toggle}
        >
          {theme === "dark" ? <Sun className="mr-1 h-4 w-4" /> : <Moon className="mr-1 h-4 w-4" />}
          테마
        </Button>
      </div>
    </div>
  );
}

export function StudioLayout() {
  return (
    <div className="flex min-h-screen bg-background">
      <aside className="hidden w-[220px] shrink-0 lg:block">
        <div className="sticky top-0 h-screen">
          <SidebarContent />
        </div>
      </aside>
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}
