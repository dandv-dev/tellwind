import { ArrowUp, MessageSquare, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { FileIcon, LinkIcon } from "../../brief/bits";
import { Spinner } from "../../components/ui";
import { api, ApiError, fileHref } from "../../lib/api";
import { domainOf, fmtCost, fmtDate } from "../../lib/format";
import type { Brief } from "../../lib/types";
import { useWorkspace } from "./Layout";

export interface AnswerSource {
  ref: number;
  kind: "workspace" | "web";
  title: string;
  url: string;
  source: string;
  date: string | null;
  file_id: string | null;
  item_id: string | null;
}
export interface QA {
  id: string;
  question: string;
  created_at: string;
  cost_usd: number;
  answer: { claims: { text: string; refs: number[] }[]; sources: AnswerSource[]; used_web: boolean; error?: string };
}

/** Floating entry point: always within reach while reading the brief. */
export function AskButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      onClick={onClick}
      aria-label={t("qa.title")}
      className="fixed z-30 bottom-4 right-4 sm:bottom-6 sm:right-6 h-12 w-12 sm:w-auto sm:pl-4 sm:pr-5 rounded-full bg-surface border border-line-strong shadow-pop text-ink inline-flex items-center justify-center gap-2 text-[14px] font-medium hover:bg-surface-2 transition-colors duration-150 ease-out"
    >
      <MessageSquare size={18} strokeWidth={1.5} />
      <span className="hidden sm:inline">{t("qa.title")}</span>
    </button>
  );
}

/**
 * Questions about the brief live in a side panel (a sheet on phones), so they can
 * be asked from anywhere on the page and the answers never push the brief around.
 */
export function AskPanel({ brief, open, onClose, prefill }: { brief: Brief; open: boolean; onClose: () => void; prefill?: { text: string; n: number } | null }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [stage, setStage] = useState(0);
  const [asking, setAsking] = useState<string | null>(null);
  const input = useRef<HTMLTextAreaElement>(null);
  const scroller = useRef<HTMLDivElement>(null);

  // "Ask about this topic": fill the question; the parent opens the panel.
  useEffect(() => {
    if (prefill) setQ(prefill.text);
  }, [prefill]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const id = window.setTimeout(() => input.current?.focus(), 350);
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
      window.clearTimeout(id);
    };
  }, [open, onClose]);

  const history = useQuery({
    queryKey: ["questions", ws.id],
    queryFn: () => api<{ questions: QA[] }>(`/workspaces/${ws.id}/questions`).then((r) => r.questions),
    enabled: open,
  });
  const ask = useMutation({
    mutationFn: (question: string) => api<QA>(`/workspaces/${ws.id}/ask`, { body: { question, brief_date: brief.date } }),
    onMutate: (question) => setAsking(question),
    onSuccess: (r) => {
      qc.setQueryData<QA[]>(["questions", ws.id], (old) => [r, ...(old ?? [])]);
      setQ("");
    },
    onSettled: () => setAsking(null),
  });
  useEffect(() => {
    if (!ask.isPending) return setStage(0);
    const id = window.setTimeout(() => setStage(1), 6000);
    return () => window.clearTimeout(id);
  }, [ask.isPending]);

  // Oldest first, newest at the bottom, next to the input.
  const thread = [...(history.data ?? []).slice(0, 10)].reverse();
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [thread.length, asking, open]);

  const send = (text: string) => {
    if (text.trim().length > 2 && !ask.isPending) ask.mutate(text.trim());
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(q);
  };

  // Starting points taken from today's brief: what changed, then what moves most.
  const moving = [...brief.topics]
    .filter((x) => x.verdict === "rising" || x.verdict === "fading")
    .sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const changed = brief.changes.map((c) => brief.topics.find((x) => x.id === c.topic_id)).filter(Boolean) as Brief["topics"];
  const suggestions = [...new Set([...changed, ...moving].map((x) => t("qa.aboutTopic", { name: x.name })))].slice(0, 3);

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
          <div className="absolute inset-0 bg-[#0b1520]/40 backdrop-blur-[2px]" onClick={onClose} />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={t("qa.title")}
            className="absolute right-0 top-0 bottom-0 w-full sm:w-[min(520px,92vw)] bg-bg sm:border-l border-line shadow-pop flex flex-col"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <header className="px-5 py-4 border-b border-line flex items-start gap-4">
              <div className="flex-1 min-w-0">
                <h2 className="text-[18px] font-medium text-ink">{t("qa.title")}</h2>
                <p className="text-[13px] text-muted mt-1">{t("qa.hint")}</p>
              </div>
              <button onClick={onClose} aria-label={t("common.close")} className="w-8 h-8 shrink-0 rounded-[10px] flex items-center justify-center text-muted hover:text-ink hover:bg-surface-2 transition-colors duration-150 ease-out">
                <X size={16} strokeWidth={1.5} />
              </button>
            </header>

            <div ref={scroller} className="flex-1 overflow-y-auto px-5 py-5 flex flex-col gap-4">
              {history.isLoading ? (
                <div className="py-10 flex justify-center text-muted"><Spinner /></div>
              ) : thread.length === 0 && !asking ? (
                <div className="mt-auto flex flex-col gap-2">
                  <p className="text-[13px] text-muted mb-1">{t("qa.tryAsking")}</p>
                  {suggestions.map((s) => (
                    <button
                      key={s}
                      onClick={() => send(s)}
                      className="text-left rounded-xl border border-line bg-surface px-4 py-3 text-[14px] text-ink hover:border-line-strong transition-colors duration-150 ease-out"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              ) : (
                <>
                  {thread.map((x) => <Answer key={x.id} qa={x} />)}
                  {asking && (
                    <div className="rounded-xl border border-line bg-surface p-4">
                      <div className="text-[13px] font-medium text-ink mb-2">“{asking}”</div>
                      <p className="text-[13px] text-muted inline-flex items-center gap-2">
                        <Spinner className="w-4 h-4" />
                        {stage === 0 ? t("qa.thinking") : t("qa.searchingWeb")}
                      </p>
                    </div>
                  )}
                </>
              )}
              {ask.isError && <p className="text-[13px] text-fading">{(ask.error as ApiError).status === 429 ? t("qa.limit") : t("common.error")}</p>}
            </div>

            <form onSubmit={submit} className="border-t border-line px-5 py-4 flex items-end gap-3 bg-bg">
              <label className="flex-1 min-w-0">
                <span className="sr-only">{t("qa.title")}</span>
                <textarea
                  ref={input}
                  value={q}
                  rows={2}
                  onChange={(e) => setQ(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send(q);
                    }
                  }}
                  placeholder={t("qa.placeholder")}
                  maxLength={500}
                  className="block w-full resize-none rounded-[10px] border border-line-strong bg-surface px-3.5 py-2.5 text-[14px] leading-5 text-ink placeholder:text-faint outline-none focus:border-accent focus:ring-4 focus:ring-accent/15 transition-[border-color,box-shadow] duration-150 ease-out"
                />
              </label>
              <button
                type="submit"
                disabled={ask.isPending || q.trim().length < 3}
                aria-label={t("qa.ask")}
                title={t("qa.ask")}
                className="h-11 w-11 shrink-0 rounded-[10px] bg-accent text-accent-ink hover:brightness-110 active:scale-[0.98] transition-[filter,transform] duration-150 ease-out disabled:opacity-50 inline-flex items-center justify-center"
              >
                {ask.isPending ? <Spinner className="w-4 h-4" /> : <ArrowUp size={18} strokeWidth={1.75} />}
              </button>
            </form>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function Answer({ qa }: { qa: QA }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const a = qa.answer;
  const src = new Map(a.sources.map((s) => [s.ref, s]));
  const wsSources = a.sources.filter((s) => s.kind === "workspace");
  const webSources = a.sources.filter((s) => s.kind === "web");
  const href = (s: AnswerSource) => (s.kind === "workspace" && s.file_id ? fileHref(ws.id, s.file_id, true) : s.url);
  return (
    <motion.article initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="rounded-xl bg-surface border border-line p-4">
      <div className="text-[13px] font-medium text-ink mb-2">“{qa.question}”</div>
      {a.error ? (
        <p className="text-[13px] text-muted">{a.error === "not_enough" ? t("qa.notEnough") : t("qa.failed")}</p>
      ) : (
        <div className="flex flex-col gap-2">
          {a.claims.map((c, i) => (
            <p key={i} className="text-[14px] leading-relaxed text-ink">
              {c.text}{" "}
              {c.refs.map((r) => {
                const s = src.get(r);
                if (!s) return null;
                return (
                  <a
                    key={r}
                    href={href(s)}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={s.title}
                    className={`reading inline-flex items-center justify-center min-w-[20px] h-[18px] px-1 mx-0.5 rounded-[5px] text-[12px] align-[2px] hover:text-ink transition-colors duration-150 ease-out ${
                      s.kind === "web" ? "bg-surface-2 text-muted border border-dashed border-line-strong" : "bg-surface-2 text-muted border border-line"
                    }`}
                  >
                    {r}
                  </a>
                );
              })}
            </p>
          ))}
        </div>
      )}
      <p className="text-[12px] text-faint mt-3">
        {a.used_web ? t("qa.usedWeb") : t("qa.noWeb")} · {t("qa.cost", { cost: fmtCost(qa.cost_usd) })}
      </p>
      {(wsSources.length > 0 || webSources.length > 0) && (
        <div className="flex flex-col gap-3 mt-3 pt-3 border-t border-line">
          {[
            { title: t("qa.workspaceSources"), list: wsSources, web: false },
            { title: t("qa.webSources"), list: webSources, web: true },
          ]
            .filter((g) => g.list.length)
            .map((g) => (
              <div key={g.title}>
                <div className="text-[12px] font-medium text-faint mb-1.5 flex items-center gap-1.5">
                  <span className={`w-2 h-2 rounded-sm ${g.web ? "border border-dashed border-faint" : "border border-line-strong bg-surface-2"}`} />
                  {g.title}
                </div>
                <ol className="flex flex-col gap-1">
                  {g.list.map((s) => (
                    <li key={s.ref} className="text-[13px] flex gap-2">
                      <span className="text-faint reading w-4 shrink-0 text-right">{s.ref}</span>
                      <a href={href(s)} target="_blank" rel="noopener noreferrer" className="text-ink hover:underline underline-offset-4 decoration-line-strong min-w-0">
                        <span className="line-clamp-1">{s.title}</span>
                        <span className="text-[12px] text-faint inline-flex items-center gap-1">
                          {s.file_id ? <FileIcon className="inline" /> : <LinkIcon />}
                          {s.source || domainOf(s.url)}
                          {s.date && ` · ${fmtDate(s.date)}`}
                        </span>
                      </a>
                    </li>
                  ))}
                </ol>
              </div>
            ))}
        </div>
      )}
    </motion.article>
  );
}
