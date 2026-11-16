// Entry for the downloadable brief (brief-<date>.html). Same components as the
// Brief tab; the data is embedded by the backend in <script id="brief-data">.
import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import { useTranslation } from "react-i18next";
import "./fonts-standalone.css";
import "./index.css";
import { BriefView } from "./brief/BriefView";
import { setupI18n } from "./i18n";
import type { Brief } from "./lib/types";
import { LOGO_SVG } from "./components/logoSvg";

setupI18n("en");

function readBrief(): Brief | null {
  const el = document.getElementById("brief-data");
  if (!el?.textContent) return null;
  try {
    return JSON.parse(el.textContent) as Brief;
  } catch {
    return null;
  }
}

function App() {
  const { t } = useTranslation();
  const brief = readBrief();
  const [theme, setTheme] = useState(() =>
    window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light",
  );
  document.documentElement.dataset.theme = theme;
  if (!brief) return <p style={{ padding: 32 }}>No brief data.</p>;
  document.title = `${brief.workspace.subject} · ${brief.date} · Tellwind`;
  return (
    <div className="min-h-dvh">
      <div className="border-b border-line bg-bg/85 backdrop-blur-md sticky top-0 z-20">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center justify-between">
          <span className="h-7 w-[124px]" dangerouslySetInnerHTML={{ __html: LOGO_SVG[theme === "dark" ? "dark" : "light"] }} />
          <div className="flex items-center gap-3 text-[12px] text-faint">
            <span className="hidden sm:inline">{brief.workspace.name}</span>
            <button
              onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
              className="h-8 rounded-[10px] border border-line px-3 text-muted hover:text-ink transition-colors duration-150 ease-out"
            >
              {theme === "dark" ? t("common.light") : t("common.dark")}
            </button>
          </div>
        </div>
      </div>
      <main className="max-w-6xl mx-auto px-4 sm:px-6 pt-6 pb-16 sm:pt-8">
        <BriefView brief={brief} />
        <footer className="mt-10 pt-5 border-t border-line text-[12px] text-faint flex flex-wrap gap-x-4 gap-y-1">
          <span>{t("brief.footer", { workspace: brief.workspace.name })}</span>
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
