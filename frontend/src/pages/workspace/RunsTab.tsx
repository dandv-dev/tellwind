import { Check, ChevronDown, Play } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "motion/react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button, Card, Spinner, Switch } from "../../components/ui";
import { api } from "../../lib/api";
import { fmtCost, fmtDateTime, fmtDay, fmtDuration } from "../../lib/format";
import type { Run, RunStep, Workspace } from "../../lib/types";
import { can, useWorkspace } from "./Layout";

export default function RunsTab() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const runs = useQuery({
    queryKey: ["runs", ws.id],
    queryFn: () => api<{ runs: Run[] }>(`/workspaces/${ws.id}/runs?limit=60`).then((r) => r.runs),
    refetchInterval: (q) => (q.state.data?.some((r) => r.status === "running" || r.status === "queued") ? 1500 : false),
  });
  const active = runs.data?.find((r) => r.status === "running" || r.status === "queued");
  const prevActive = usePrevious(active?.id);
  useEffect(() => {
    // A run just finished: refresh the brief, files and list badges.
    if (prevActive && !active) {
      qc.invalidateQueries({ queryKey: ["briefs", ws.id] });
      qc.invalidateQueries({ queryKey: ["brief", ws.id] });
      qc.invalidateQueries({ queryKey: ["files", ws.id] });
      qc.invalidateQueries({ queryKey: ["workspaces"] });
    }
  }, [active, prevActive, qc, ws.id]);

  const start = useMutation({
    mutationFn: () => api<Run>(`/workspaces/${ws.id}/runs`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["runs", ws.id] }),
  });
  const member = can(ws.role, "member");
  const done = (runs.data ?? []).filter((r) => r !== active);
  const total = done.reduce((a, r) => a + (r.cost_usd || 0), 0);

  return (
    <div className="flex flex-col gap-8 sm:gap-10">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <h1 className="text-[28px] sm:text-[32px] font-medium text-ink tracking-[-0.02em]">{t("runs.tab")}</h1>
        <div className="flex flex-col-reverse sm:flex-row sm:items-center gap-2">
          <Schedule ws={ws} editable={member} />
          {member ? (
            <Button onClick={() => start.mutate()} loading={start.isPending} disabled={!!active} className="w-full sm:w-auto">
              {active ? t("runs.runningNow") : (
                <>
                  <Play size={16} strokeWidth={1.75} />
                  {t("runs.runNow")}
                </>
              )}
            </Button>
          ) : (
            <span className="text-[13px] text-faint">{t("runs.viewerNote")}</span>
          )}
        </div>
      </div>

      {active && <ActiveRun runId={active.id} />}

      <section>
        <h2 className="text-[18px] font-medium text-ink mb-4">{t("runs.past")}</h2>
        {runs.isLoading ? (
          <div className="py-10 flex justify-center text-muted"><Spinner /></div>
        ) : done.length === 0 ? (
          <p className="text-[14px] text-muted">{t("runs.noRuns")}</p>
        ) : (
          <Card className="overflow-hidden">
            <div className={`hidden sm:grid ${ROW} px-4 h-10 items-center border-b border-line text-[12px] text-muted`}>
              <span>{t("runs.cols.date")}</span>
              <span>{t("runs.cols.status")}</span>
              <span>{t("runs.cols.trigger")}</span>
              <span className="text-right">{t("runs.cols.duration")}</span>
              <span className="text-right">{t("runs.cols.cost")}</span>
              <span />
            </div>
            <div className="divide-y divide-line">
              {done.map((r) => <RunRow key={r.id} r={r} />)}
            </div>
            <div className="px-4 h-11 flex items-center justify-end border-t border-line text-[12px] text-muted tabular-nums">
              {t("runs.totalCost", { count: done.length, cost: fmtCost(total) })}
            </div>
          </Card>
        )}
      </section>
    </div>
  );
}

/** Shared column template for the header and every run row. */
const ROW = "grid-cols-[140px_96px_minmax(0,1fr)_88px_80px_16px] gap-x-4";

function usePrevious<T>(v: T) {
  const [prev, setPrev] = useState<T | undefined>(undefined);
  const [cur, setCur] = useState(v);
  if (v !== cur) {
    setPrev(cur);
    setCur(v);
  }
  return prev;
}

const STATUS_CLS: Record<Run["status"], string> = {
  queued: "bg-surface-2 text-muted",
  running: "bg-accent-soft text-accent",
  succeeded: "bg-rising-soft text-rising",
  failed: "bg-fading-soft text-fading",
};

function RunRow({ r }: { r: Run }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className={`w-full text-left px-4 py-3 grid grid-cols-[minmax(0,1fr)_auto_16px] gap-x-3 gap-y-1 sm:grid-cols-[140px_96px_minmax(0,1fr)_88px_80px_16px] sm:gap-x-4 items-center hover:bg-surface-2 transition-colors duration-150 ease-out`}
      >
        <span className="text-[13px] text-ink reading">{fmtDay(r.as_of)}</span>
        <span className={`justify-self-end sm:justify-self-start w-fit rounded-md px-2 h-6 inline-flex items-center text-[12px] font-medium ${STATUS_CLS[r.status]}`}>{t(`runs.status.${r.status}`)}</span>
        <ChevronDown size={16} strokeWidth={1.5} className={`row-span-2 sm:row-span-1 sm:order-last text-faint transition-transform duration-200 ease-out ${open ? "rotate-180" : ""}`} />
        <span className="hidden sm:block text-[12px] text-muted truncate">{t(`runs.trigger.${r.trigger}`, { defaultValue: r.trigger })}{r.by ? ` · ${r.by}` : ""}</span>
        <span className="text-[12px] text-muted reading sm:text-right">{fmtDuration(r.started_at, r.finished_at)}</span>
        <span className="text-[13px] text-ink reading text-right">{fmtCost(r.cost_usd)}</span>
      </button>
      {open && (
        <div className="bg-surface-2/40 border-t border-line">
          {r.error && <p className="px-4 pt-3 text-[13px] text-fading">{r.error}</p>}
          <Steps steps={r.steps} table />
          <div className="px-4 py-3 border-t border-line flex flex-col sm:flex-row sm:items-center gap-3 sm:justify-between">
            <span className="text-[12px] text-faint tabular-nums">{t("runs.startedAt", { when: fmtDateTime(r.started_at) })}</span>
            <div className="flex gap-2">
              {r.brief_id && (
                <Link to={`..?date=${r.as_of}`} relative="path" className="h-8 px-3 rounded-[10px] border border-line-strong bg-surface text-[13px] font-medium text-ink inline-flex items-center hover:bg-surface-2 transition-colors duration-150 ease-out">
                  {t("runs.viewBrief")}
                </Link>
              )}
              <Link to="../files?view=runs" relative="path" className="h-8 px-3 rounded-[10px] text-[13px] font-medium text-muted inline-flex items-center hover:text-ink hover:bg-surface-2 transition-colors duration-150 ease-out">
                {t("runs.viewFiles")}
              </Link>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function ActiveRun({ runId }: { runId: string }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["run", ws.id, runId],
    queryFn: () => api<Run>(`/workspaces/${ws.id}/runs/${runId}`),
    refetchInterval: 1200,
  });
  const r = q.data;
  return (
    <Card className="p-5 border-accent/40">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <span className="relative flex w-2.5 h-2.5">
            <span className="absolute inset-0 rounded-full bg-accent animate-ping opacity-60" />
            <span className="relative w-2.5 h-2.5 rounded-full bg-accent" />
          </span>
          <h2 className="text-[15px] font-medium text-ink">{t("runs.current")}</h2>
        </div>
        {r && <span className="text-[13px] text-muted reading">{fmtCost(r.cost_usd)}</span>}
      </div>
      {r ? <Steps steps={r.steps} live /> : <Spinner />}
    </Card>
  );
}

/**
 * One line per step: what it did, then how long it took. In the runs table the
 * columns follow the table's own (step under date and status, result under
 * "started", time under "duration").
 */
function Steps({ steps, live = false, table = false }: { steps: RunStep[]; live?: boolean; table?: boolean }) {
  const { t } = useTranslation();
  return (
    <ol className={table ? "py-2" : "-mx-1"}>
      {steps.map((s) => {
        const pending = s.status === "pending";
        const took = s.started_at && s.finished_at ? fmtDuration(s.started_at, s.finished_at) : "";
        const msg = s.message && !pending ? (
          <motion.span key={s.message} initial={live ? { opacity: 0 } : false} animate={{ opacity: 1 }} className={s.status === "failed" ? "text-fading" : "text-muted"}>
            {s.message}
          </motion.span>
        ) : null;
        return (
          <li
            key={s.key}
            className={`grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 py-2 sm:py-0 sm:min-h-9 sm:items-center ${
              table ? "px-4 sm:grid-cols-[140px_96px_minmax(0,1fr)_88px_80px_16px] sm:gap-x-4" : "px-1 sm:grid-cols-[240px_minmax(0,1fr)_64px] sm:gap-x-4"
            }`}
          >
            <span className={`flex items-start sm:items-center gap-3 min-w-0 ${table ? "sm:col-span-2" : ""}`}>
              <StepDot status={s.status} />
              <span className="min-w-0">
                <span className={`block text-[13px] font-medium ${pending ? "text-faint" : "text-ink"}`}>{t(`runs.steps.${s.key}`)}</span>
                {msg && <span className="sm:hidden block text-[12px] mt-0.5">{msg}</span>}
              </span>
            </span>
            <span className="hidden sm:block text-[12px] truncate">{msg}</span>
            <span className="text-[12px] text-faint reading text-right">{took}</span>
          </li>
        );
      })}
    </ol>
  );
}

function StepDot({ status }: { status: RunStep["status"] }) {
  if (status === "running") return <Spinner className="w-4 h-4 shrink-0 text-accent" />;
  if (status === "done")
    return (
      <span className="w-4 h-4 shrink-0 rounded-full bg-rising text-white flex items-center justify-center">
        <Check size={10} strokeWidth={2.5} />
      </span>
    );
  if (status === "failed") return <span className="w-4 h-4 shrink-0 rounded-full bg-fading text-white text-[12px] font-medium flex items-center justify-center">!</span>;
  return <span className="w-4 h-4 shrink-0 rounded-full border-2 border-line-strong" />;
}

function Schedule({ ws, editable }: { ws: Workspace; editable: boolean }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [enabled, setEnabled] = useState(ws.schedule.enabled);
  const [time, setTime] = useState(ws.schedule.time);
  const save = useMutation({
    mutationFn: (body: { enabled: boolean; time: string }) => api(`/workspaces/${ws.id}/schedule`, { method: "PUT", body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["workspace", ws.id] }),
  });
  const update = (e: boolean, tm: string) => {
    setEnabled(e);
    setTime(tm);
    if (editable) save.mutate({ enabled: e, time: tm });
  };
  return (
    <div
      className="h-10 rounded-[10px] border border-line bg-surface shadow-card pl-3 pr-2 flex items-center gap-2 [&>input]:ml-auto sm:[&>input]:ml-0"
      title={t("runs.scheduleHint")}
    >
      <Switch checked={enabled} onChange={(v) => update(v, time)} disabled={!editable} label={t("runs.schedule")} />
      <span className={`text-[13px] whitespace-nowrap ${enabled ? "text-ink" : "text-muted"}`}>{enabled ? t("runs.dailyAt") : t("runs.scheduleOffLong")}</span>
      <input
        type="time"
        value={time}
        aria-label={t("runs.timeUtc")}
        disabled={!editable || !enabled}
        onChange={(e) => e.target.value && update(enabled, e.target.value)}
        className="h-8 rounded-md bg-transparent px-1 text-[13px] text-ink reading outline-none focus-visible:ring-2 focus-visible:ring-accent/40 disabled:opacity-50"
      />
      <span className="text-[12px] text-faint">UTC</span>
      {save.isPending && <Spinner className="w-3.5 h-3.5 text-muted" />}
    </div>
  );
}
