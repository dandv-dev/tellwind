import { useQuery } from "@tanstack/react-query";
import { createContext, useContext } from "react";
import { useTranslation } from "react-i18next";
import { Link, NavLink, Outlet, useParams } from "react-router-dom";
import { TopBar } from "../../components/TopBar";
import { RoleBadge, Spinner } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import type { Role, Workspace } from "../../lib/types";

const Ctx = createContext<Workspace | null>(null);
export const useWorkspace = () => useContext(Ctx)!;
export const can = (role: Role, min: Role) => ["viewer", "member", "owner"].indexOf(role) >= ["viewer", "member", "owner"].indexOf(min);

export default function WorkspaceLayout() {
  const { wid = "" } = useParams();
  const { t } = useTranslation();
  const q = useQuery({ queryKey: ["workspace", wid], queryFn: () => api<Workspace>(`/workspaces/${wid}`), retry: false });

  if (q.error) {
    const nf = q.error instanceof ApiError && q.error.status === 404;
    return (
      <div className="min-h-dvh">
        <TopBar logoTo="/app" />
        <div className="max-w-md mx-auto py-24 text-center">
          <h1 className="text-[20px] font-medium text-ink">{nf ? t("notFound.title") : t("common.error")}</h1>
          <Link to="/app" className="text-ink font-medium mt-3 inline-block hover:underline underline-offset-4 decoration-line-strong">{t("topbar.workspaces")} →</Link>
        </div>
      </div>
    );
  }
  const ws = q.data;
  const tabs = [
    { to: "", label: t("brief.tab"), end: true },
    { to: "runs", label: t("runs.tab") },
    { to: "files", label: t("files.tab") },
    { to: "team", label: t("team.tab") },
  ];

  const tabLinks = (h: string) =>
    tabs.map((tb) => (
      <NavLink
        key={tb.to}
        to={tb.to}
        end={tb.end}
        className={({ isActive }) =>
          `relative px-3 ${h} flex items-center text-[14px] font-medium whitespace-nowrap transition-colors duration-150 ease-out ${
            isActive ? "text-ink after:absolute after:inset-x-3 after:bottom-0 after:h-[2px] after:bg-accent after:rounded-full" : "text-muted hover:text-ink"
          }`
        }
      >
        {tb.label}
      </NavLink>
    ));

  return (
    <div className="min-h-dvh">
      {/* Desktop: one bar (logo, workspace, tabs, controls). Phones and tablets: tabs get their own row. */}
      <TopBar logoTo="/app">
        {ws && (
          <>
            <div className="flex items-center gap-2 min-w-0 ml-3 pl-3 border-l border-line h-6 self-center">
              <span className="text-[14px] font-medium text-ink truncate" title={ws.subject}>{ws.name}</span>
              <span className="hidden sm:inline-flex"><RoleBadge role={ws.role} label={t(`common.roles.${ws.role}`)} /></span>
            </div>
            <nav className="hidden lg:flex items-stretch ml-6" aria-label="Workspace">
              {tabLinks("h-16")}
            </nav>
          </>
        )}
      </TopBar>
      <div className="lg:hidden sticky top-16 z-20 bg-bg/85 backdrop-blur-md border-b border-line">
        <nav className="max-w-6xl mx-auto px-1 sm:px-3 flex overflow-x-auto scrollbar-none" aria-label="Workspace">
          {tabLinks("h-11")}
        </nav>
      </div>
      <main className="max-w-6xl mx-auto px-4 sm:px-6 pt-6 pb-16 sm:pt-8">
        {!ws ? (
          <div className="py-24 flex justify-center text-muted"><Spinner /></div>
        ) : (
          <Ctx.Provider value={ws}>
            <Outlet />
          </Ctx.Provider>
        )}
      </main>
    </div>
  );
}
