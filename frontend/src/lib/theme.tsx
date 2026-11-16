import { createContext, useCallback, useContext, useState, type ReactNode } from "react";

export type Theme = "light" | "dark";

const Ctx = createContext<{ theme: Theme; toggle: () => void }>({ theme: "light", toggle: () => {} });

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<Theme>(() => (document.documentElement.dataset.theme === "dark" ? "dark" : "light"));
  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    const root = document.documentElement;
    root.classList.add("theme-anim");
    root.dataset.theme = next;
    window.setTimeout(() => root.classList.remove("theme-anim"), 400);
    try {
      localStorage.setItem("tw-theme", next);
    } catch {
      /* ignore */
    }
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", next === "dark" ? "#0b1520" : "#F5F1EA");
    setTheme(next);
  }, [theme]);
  return <Ctx.Provider value={{ theme, toggle }}>{children}</Ctx.Provider>;
}

export const useTheme = () => useContext(Ctx);
