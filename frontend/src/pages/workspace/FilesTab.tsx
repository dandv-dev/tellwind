import { Download, Upload, X } from "lucide-react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type DragEvent, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { FileIcon, LinkIcon } from "../../brief/bits";
import { Button, Card, Spinner } from "../../components/ui";
import { api, fileHref } from "../../lib/api";
import { domainOf, fmtBytes, fmtDate, fmtDateTime, fmtDay } from "../../lib/format";
import type { WFile } from "../../lib/types";
import { can, useWorkspace } from "./Layout";

interface NewsItem {
  id: string;
  title: string;
  url: string;
  source: string;
  collector: string;
  published_at: string;
  also: number;
}

type View = "uploads" | "runs" | "news";

export default function FilesTab() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const view = (["uploads", "runs", "news"].includes(params.get("view") ?? "") ? params.get("view") : "uploads") as View;
  const setView = (v: View) => {
    const p = new URLSearchParams(params);
    if (v === "uploads") p.delete("view");
    else p.set("view", v);
    setParams(p, { replace: true });
  };
  const files = useQuery({
    queryKey: ["files", ws.id],
    queryFn: () => api<{ files: WFile[] }>(`/workspaces/${ws.id}/files`).then((r) => r.files),
  });
  const newsTotal = useQuery({
    queryKey: ["items-total", ws.id],
    queryFn: () => api<{ total: number }>(`/workspaces/${ws.id}/items?limit=1`).then((r) => r.total),
  });
  const upload = useUpload();
  const member = can(ws.role, "member");

  const uploads = (files.data ?? []).filter((f) => f.kind === "upload");
  const outputs = (files.data ?? []).filter((f) => f.kind !== "upload");
  const byDate = new Map<string, WFile[]>();
  for (const f of outputs) {
    const k = f.brief_date ?? f.created_at.slice(0, 10);
    byDate.set(k, [...(byDate.get(k) ?? []), f]);
  }

  const views: { key: View; label: string; n?: number }[] = [
    { key: "uploads", label: t("files.tabUploads"), n: uploads.length },
    { key: "runs", label: t("files.tabRuns"), n: byDate.size },
    { key: "news", label: t("files.tabNews"), n: newsTotal.data },
  ];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-end justify-between gap-4 mb-4 sm:mb-6">
        <h1 className="text-[28px] sm:text-[32px] font-medium text-ink tracking-[-0.02em]">{t("files.tab")}</h1>
        {member && (
          <Button onClick={() => { setView("uploads"); upload.pick(); }} loading={upload.busy > 0}>
            {upload.busy === 0 && <Upload size={16} strokeWidth={1.75} />}
            {upload.busy ? t("files.uploading") : t("files.upload")}
          </Button>
        )}
      </div>
      {upload.input}

      <div role="tablist" aria-label={t("files.tab")} className="flex w-full sm:w-fit p-1 rounded-[10px] bg-surface-2 overflow-x-auto scrollbar-none">
        {views.map((v) => (
          <button
            key={v.key}
            role="tab"
            aria-selected={view === v.key}
            onClick={() => setView(v.key)}
            className={`flex-1 sm:flex-none h-8 px-3 rounded-md text-[13px] font-medium whitespace-nowrap inline-flex items-center justify-center gap-2 transition-colors duration-150 ease-out ${
              view === v.key ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"
            }`}
          >
            {v.label}
            {v.n != null && <span className="reading text-[12px] text-faint font-normal">{v.n}</span>}
          </button>
        ))}
      </div>

      {view === "uploads" && (
        <section aria-label={t("files.uploads")}>
          <DropZone onFiles={upload.send} enabled={member}>
            {files.isLoading ? (
              <div className="py-10 flex justify-center text-muted"><Spinner /></div>
            ) : uploads.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-line-strong px-6 py-12 text-center">
                <p className="text-[14px] text-ink font-medium">{t("files.noUploads")}</p>
                {member && <p className="text-[13px] text-muted mt-1">{t("files.dropHere")}</p>}
              </div>
            ) : (
              <Card className="divide-y divide-line">
                {uploads.map((f) => <UploadRow key={f.id} f={f} />)}
              </Card>
            )}
          </DropZone>
          <p className="text-[12px] text-faint mt-3">{member ? `${t("files.uploadHint")} ${t("files.dragHint")}` : t("files.uploadHint")}</p>
          {upload.err && <p className="text-[12px] text-fading mt-2">{upload.err}</p>}
        </section>
      )}

      {view === "runs" && (
        <section aria-label={t("files.outputs")}>
          {files.isLoading ? null : outputs.length === 0 ? (
            <p className="text-[14px] text-muted">{t("files.noOutputs")}</p>
          ) : (
            <Card className="overflow-hidden">
              <div className="hidden sm:grid grid-cols-[140px_repeat(3,minmax(0,1fr))] gap-4 px-4 h-10 items-center border-b border-line text-[12px] text-muted">
                <span>{t("runs.cols.date")}</span>
                <span>{t("files.brief")}</span>
                <span>{t("files.trace")}</span>
                <span>{t("files.newsCsv")}</span>
              </div>
              <div className="divide-y divide-line">
                {[...byDate.entries()].map(([d, fs]) => (
                  <div key={d} className="px-4 py-3 grid grid-cols-1 sm:grid-cols-[140px_repeat(3,minmax(0,1fr))] gap-x-4 gap-y-2 sm:items-center">
                    <span className="text-[13px] text-ink reading">{fmtDay(d)}</span>
                    {(["brief", "trace", "news"] as const).map((k) => {
                      const f = fs.find((x) => x.kind === k);
                      return f ? (
                        <a
                          key={k}
                          href={fileHref(ws.id, f.id, k !== "brief")}
                          target={k === "brief" ? undefined : "_blank"}
                          rel="noreferrer"
                          title={f.filename}
                          className="group inline-flex items-center gap-2 text-[13px] text-ink w-fit"
                        >
                          <Download size={14} strokeWidth={1.5} className="text-faint group-hover:text-ink transition-colors duration-150 ease-out" />
                          <span className="sm:hidden">{t(`files.${k === "news" ? "newsCsv" : k}`)}</span>
                          <span className="hidden sm:inline group-hover:underline underline-offset-4 decoration-line-strong truncate">{f.filename}</span>
                          <span className="reading text-[12px] text-faint">{fmtBytes(f.size)}</span>
                        </a>
                      ) : (
                        <span key={k} className="hidden sm:block text-faint">—</span>
                      );
                    })}
                  </div>
                ))}
              </div>
            </Card>
          )}
        </section>
      )}

      {view === "news" && <NewsBrowser />}
    </div>
  );
}

/** File picker plus the upload queue, shared by the header button and the drop zone. */
function useUpload() {
  const ws = useWorkspace();
  const qc = useQueryClient();
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const send = async (list: FileList | null) => {
    if (!list?.length) return;
    setErr(null);
    for (const file of Array.from(list)) {
      setBusy((b) => b + 1);
      const form = new FormData();
      form.append("file", file);
      try {
        await api(`/workspaces/${ws.id}/files`, { form });
      } catch (e) {
        setErr(`${file.name}: ${(e as Error).message}`);
      } finally {
        setBusy((b) => b - 1);
      }
    }
    qc.invalidateQueries({ queryKey: ["files", ws.id] });
  };
  const input = <input ref={ref} type="file" multiple accept=".pdf,.docx,.txt,.md" className="hidden" onChange={(e) => send(e.target.files)} />;
  return { send, busy, err, input, pick: () => ref.current?.click() };
}

/** Files can be dropped anywhere on the uploads list. */
function DropZone({ onFiles, enabled, children }: { onFiles: (f: FileList | null) => void; enabled: boolean; children: ReactNode }) {
  const { t } = useTranslation();
  const [over, setOver] = useState(false);
  if (!enabled) return <>{children}</>;
  return (
    <div
      className="relative"
      onDragOver={(e: DragEvent) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={(e: DragEvent) => !e.currentTarget.contains(e.relatedTarget as Node) && setOver(false)}
      onDrop={(e: DragEvent) => {
        e.preventDefault();
        setOver(false);
        onFiles(e.dataTransfer.files);
      }}
    >
      {children}
      {over && (
        <div className="absolute inset-0 rounded-2xl border-2 border-dashed border-accent bg-accent-soft/90 flex items-center justify-center text-[14px] font-medium text-ink pointer-events-none">
          {t("files.dropHere")}
        </div>
      )}
    </div>
  );
}

function UploadRow({ f }: { f: WFile }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const del = useMutation({
    mutationFn: () => api(`/workspaces/${ws.id}/files/${f.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["files", ws.id] }),
  });
  const ext = f.filename.split(".").pop()?.toUpperCase();
  return (
    <div className="px-4 py-3 flex items-center gap-3">
      <span className="reading w-10 h-10 shrink-0 rounded-[10px] bg-surface-2 text-muted text-[12px] flex items-center justify-center">{ext}</span>
      <div className="min-w-0 flex-1">
        <a href={fileHref(ws.id, f.id, true)} target="_blank" rel="noreferrer" className="text-[14px] font-medium text-ink hover:underline underline-offset-4 decoration-line-strong truncate block">
          {f.filename}
        </a>
        <div className="mt-0.5 text-[12px] text-faint flex flex-wrap gap-x-2">
          <span>{fmtDateTime(f.created_at)}</span>
          {f.uploaded_by && <span>· {f.uploaded_by}</span>}
          <span>· {fmtBytes(f.size)}</span>
          <span className={!f.parse_status || f.parse_status === "ok" ? "" : "text-fading"}>· {t(`files.parse.${f.parse_status || "ok"}`, { count: f.chunks })}</span>
        </div>
      </div>
      <a href={fileHref(ws.id, f.id)} title={t("common.download")} aria-label={t("common.download")} className="h-8 w-8 sm:w-auto sm:px-2 rounded-[10px] inline-flex items-center justify-center gap-2 text-[13px] font-medium text-muted hover:text-ink hover:bg-surface-2 transition-colors duration-150 ease-out"><Download size={16} strokeWidth={1.5} /><span className="hidden sm:inline">{t("common.download")}</span></a>
      {can(ws.role, "member") && (
        <button
          onClick={() => window.confirm(t("files.deleteConfirm")) && del.mutate()}
          className="w-8 h-8 rounded-[10px] flex items-center justify-center text-faint hover:text-fading hover:bg-fading-soft transition-colors duration-150 ease-out"
          aria-label={t("common.delete")}
        >
          <X size={16} strokeWidth={1.5} />
        </button>
      )}
    </div>
  );
}

function NewsBrowser() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const [q, setQ] = useState("");
  const [limit, setLimit] = useState(25);
  const news = useQuery({
    queryKey: ["items", ws.id, q, limit],
    queryFn: () => api<{ total: number; items: NewsItem[] }>(`/workspaces/${ws.id}/items?q=${encodeURIComponent(q)}&limit=${limit}`),
    placeholderData: keepPreviousData,
  });
  return (
    <section aria-label={t("files.news")}>
      <div className="mb-3">
        <input
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setLimit(25);
          }}
          placeholder={t("files.search")}
          className="h-10 w-full sm:w-80 rounded-[10px] border border-line-strong bg-surface px-3 text-[13px] text-ink placeholder:text-faint outline-none focus:border-accent focus:ring-4 focus:ring-accent/15 transition-[border-color,box-shadow] duration-150 ease-out"
        />
      </div>
      <Card className="divide-y divide-line">
        {news.data?.items.map((i) => (
          <a key={i.id} href={i.url} target="_blank" rel="noopener noreferrer" className="px-4 py-3 flex items-start gap-3 hover:bg-surface-2 transition-colors duration-150 ease-out group">
            <span className="w-14 shrink-0 text-[12px] text-faint reading pt-0.5">{fmtDate(i.published_at)}</span>
            <span className="min-w-0 flex-1">
              <span className="text-[13px] text-ink group-hover:underline underline-offset-4 decoration-line-strong line-clamp-1">{i.title}</span>
              <span className="text-[12px] text-faint inline-flex items-center gap-1">
                {i.collector === "upload" ? <FileIcon /> : <LinkIcon />} {i.source || domainOf(i.url)} · {i.collector === "hn" ? "Hacker News" : i.collector === "gnews" ? "Google News" : i.collector}
                {i.also > 0 && ` · ${t("brief.alsoCovered", { count: i.also })}`}
              </span>
            </span>
          </a>
        ))}
        {news.data && news.data.total > news.data.items.length && (
          <button onClick={() => setLimit(limit + 50)} className="w-full px-4 py-3 text-[13px] font-medium text-ink hover:bg-surface-2 transition-colors duration-150 ease-out">
            {t("files.more")} · {news.data.items.length}/{news.data.total}
          </button>
        )}
      </Card>
    </section>
  );
}
