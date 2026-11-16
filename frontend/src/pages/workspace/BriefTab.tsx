import { Download, MessageSquare, ScrollText, TrendingUp } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useSearchParams } from "react-router-dom";
import { BriefView, type BriefNav } from "../../brief/BriefView";
import type { BriefDay } from "../../brief/DayStrip";
import { Button, Empty, Spinner } from "../../components/ui";
import { api, fileHref } from "../../lib/api";
import type { Brief, Run, WFile } from "../../lib/types";
import { AskButton, AskPanel } from "./AskBox";
import { CompanyModal } from "./CompanyModal";
import { can, useWorkspace } from "./Layout";

const linkCls =
  "inline-flex items-center gap-1.5 text-[13px] text-muted hover:text-ink transition-colors duration-150 ease-out";

export default function BriefTab() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const date = params.get("date");
  const [company, setCompany] = useState<string | null>(null);
  const [askFor, setAskFor] = useState<{ text: string; n: number } | null>(null);
  const [asking, setAsking] = useState(false);

  const dates = useQuery({
    queryKey: ["briefs", ws.id],
    queryFn: () => api<{ dates: (BriefDay & { id: string })[] }>(`/workspaces/${ws.id}/briefs`),
  });
  const brief = useQuery({
    queryKey: ["brief", ws.id, date ?? "latest"],
    queryFn: () =>
      api<{ brief: Brief | null }>(`/workspaces/${ws.id}/briefs/${date ?? "latest"}`).then((r) => r.brief),
    placeholderData: (prev) => prev,
  });
  const files = useQuery({
    queryKey: ["files", ws.id],
    queryFn: () => api<{ files: WFile[] }>(`/workspaces/${ws.id}/files`).then((r) => r.files),
  });

  if (brief.isLoading || dates.isLoading) return <div className="py-24 flex justify-center text-muted"><Spinner /></div>;
  if (!brief.data) return <NoBrief />;

  const b = brief.data;
  const list = dates.data?.dates ?? [];
  const idx = list.findIndex((d) => d.date === b.date);
  const go = (d: string | null) => {
    const p = new URLSearchParams(params);
    if (!d || d === list[0]?.date) p.delete("date");
    else p.set("date", d);
    setParams(p);
  };
  const out = (files.data ?? []).filter((f) => f.brief_date === b.date && f.run_id === b.run_id);
  const htmlFile = out.find((f) => f.kind === "brief");
  const traceFile = out.find((f) => f.kind === "trace");

  const nav: BriefNav = {
    days: list,
    onPick: go,
    onLatest: idx > 0 ? () => go(null) : undefined,
  };
  const actions = (
    <>
      {htmlFile && (
        <a href={fileHref(ws.id, htmlFile.id)} className={linkCls}>
          <Download size={14} strokeWidth={1.5} />
          {t("brief.downloadHtml")}
        </a>
      )}
      {traceFile && (
        <a href={fileHref(ws.id, traceFile.id, true)} target="_blank" rel="noreferrer" className={linkCls}>
          <ScrollText size={14} strokeWidth={1.5} />
          {t("brief.downloadTrace")}
        </a>
      )}
      <button onClick={() => setAsking(true)} className={linkCls}>
        <MessageSquare size={14} strokeWidth={1.5} />
        {t("qa.title")}
      </button>
    </>
  );

  return (
    <div className={`pb-16 transition-opacity ${brief.isFetching && brief.isPlaceholderData ? "opacity-60" : ""}`}>
      <BriefView
        key={b.date}
        brief={b}
        nav={nav}
        actions={actions}
        links={{ fileHref: (fid) => fileHref(ws.id, fid, true), onCompany: setCompany }}
        onAskTopic={(x) => {
          setAskFor({ text: t("qa.aboutTopic", { name: x.name }), n: (askFor?.n ?? 0) + 1 });
          setAsking(true);
        }}
      />
      <AskButton onClick={() => setAsking(true)} />
      <AskPanel brief={b} open={asking} onClose={() => setAsking(false)} prefill={askFor} />
      <CompanyModal companyId={company} onClose={() => setCompany(null)} />
    </div>
  );
}

function NoBrief() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const nav = useNavigate();
  const start = useMutation({
    mutationFn: () => api<Run>(`/workspaces/${ws.id}/runs`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["runs", ws.id] });
      nav("runs");
    },
  });
  return (
    <Empty
      title={t("brief.noBrief")}
      icon={
        <span className="w-10 h-10 rounded-xl bg-surface-2 flex items-center justify-center text-muted">
          <TrendingUp size={18} strokeWidth={1.5} />
        </span>
      }
    >
      {can(ws.role, "member") ? (
        <>
          <p>{t("brief.noBriefHint")}</p>
          <Button className="mt-5" size="lg" loading={start.isPending} onClick={() => start.mutate()}>
            {t("brief.runFirst")}
          </Button>
        </>
      ) : (
        <p>{t("brief.noBriefViewer")}</p>
      )}
    </Empty>
  );
}
