import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { useTranslation } from "react-i18next";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import "@fontsource-variable/plus-jakarta-sans/wght.css";
// Plus Jakarta Sans has no basic Cyrillic; Manrope covers RU/UA text.
import "@fontsource-variable/manrope/wght.css";
import "@fontsource-variable/jetbrains-mono/wght.css";
import "./index.css";
import { Spinner } from "./components/ui";
import { setupI18n } from "./i18n";
import { useMe } from "./lib/auth";
import { ThemeProvider } from "./lib/theme";
import Landing from "./pages/Landing";

setupI18n();

const Auth = lazy(() => import("./pages/Auth"));
const Workspaces = lazy(() => import("./pages/Workspaces"));
const Invite = lazy(() => import("./pages/Invite"));
const WorkspaceLayout = lazy(() => import("./pages/workspace/Layout"));
const BriefTab = lazy(() => import("./pages/workspace/BriefTab"));
const RunsTab = lazy(() => import("./pages/workspace/RunsTab"));
const FilesTab = lazy(() => import("./pages/workspace/FilesTab"));
const TeamTab = lazy(() => import("./pages/workspace/TeamTab"));

const qc = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1, staleTime: 15_000 } },
});

function Loading() {
  return (
    <div className="min-h-[50dvh] flex items-center justify-center text-muted">
      <Spinner />
    </div>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { data: me, isLoading } = useMe();
  const loc = useLocation();
  if (isLoading) return <Loading />;
  if (!me) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <>{children}</>;
}

function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="min-h-dvh flex flex-col items-center justify-center gap-3">
      <h1 className="text-[28px] font-medium text-ink tracking-[-0.02em]">{t("notFound.title")}</h1>
      <Link to="/" className="text-accent font-medium">{t("notFound.back")}</Link>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={qc}>
      <ThemeProvider>
        <BrowserRouter>
          <Suspense fallback={<Loading />}>
            <Routes>
              <Route path="/" element={<Landing />} />
              <Route path="/login" element={<Auth />} />
              <Route path="/invite/:token" element={<Invite />} />
              <Route path="/app" element={<RequireAuth><Workspaces /></RequireAuth>} />
              <Route path="/app/w/:wid" element={<RequireAuth><WorkspaceLayout /></RequireAuth>}>
                <Route index element={<BriefTab />} />
                <Route path="runs" element={<RunsTab />} />
                <Route path="files" element={<FilesTab />} />
                <Route path="team" element={<TeamTab />} />
              </Route>
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
