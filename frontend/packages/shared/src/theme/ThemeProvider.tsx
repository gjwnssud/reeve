import { createContext, useContext, type ReactNode } from 'react';

import { useTheme, type Theme } from '../hooks/useTheme';

type ThemeCtx = { theme: Theme; setTheme: (t: Theme) => void; toggle: () => void };
const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const value = useTheme();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useThemeContext(): ThemeCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useThemeContext must be used within ThemeProvider');
  return ctx;
}
