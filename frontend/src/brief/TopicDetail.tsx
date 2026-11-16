import { MessageSquare, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { domainOf, fmtDate, fmtPct } from "../lib/format";
import type { Brief, BriefLinks, CompanyRef, Evidence, TopicBrief } from "../lib/types";
import { Sparkline } from "./Sparkline";
import { FileIcon, LinkIcon, SignalPill, VerdictBadge, pctColor, verdictVar } from "./bits";

interface Props {
  brief: Brief;
  topic: TopicBrief | null;
  onClose: () => void;
  links?: BriefLinks;
  onAsk?: (topic: TopicBrief) => void;
}

/** Side panel (sheet on phones) with the full reasoning and every source. */
export function TopicDrawer({ brief, topic, onClose, links, onAsk }: Props) {
  useEffect(() => {
    if (!topic) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [topic, onClose]);

  return (
    <AnimatePresence>
      {topic && (
        <motion.div className="fixed inset-0 z-50" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
          <div className="absolute inset-0 bg-[#0b1520]/40 backdrop-blur-[2px]" onClick={onClose} />
          <motion.aside
            role="dialog"
            aria-modal="true"
            aria-label={topic.name}
            className="absolute right-0 top-0 bottom-0 w-full sm:w-[min(640px,92vw)] bg-bg sm:border-l border-line shadow-pop overflow-y-auto"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <TopicDetail brief={brief} topic={topic} onClose={onClose} links={links} onAsk={onAsk ? (x) => { onClose(); onAsk(x); } : undefined} />
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export function TopicDetail({ brief, topic: t, onClose, links, onAsk }: { brief: Brief; topic: TopicBrief; onClose?: () => void; links?: BriefLinks; onAsk?: (topic: TopicBrief) => void }) {
  const { t: tr } = useTranslation();
  const ev = brief.evidence;
  const sources = useMemo(() => t.sources.map((id) => ev[id]).filter(Boolean) as Evidence[], [t, ev]);
  const num = useMemo(() => new Map(sources.map((s, i) => [s.id, i + 1])), [sources]);
  const [flash, setFlash] = useState<string | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const m = t.metrics;

  const jump = (id: string) => {
    const el = listRef.current?.querySelector(`[data-ev="${id}"]`);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    setFlash(id);
    window.setTimeout(() => setFlash(null), 1400);
  };

  return (
    <div className="pb-16">
      <header className="sticky top-0 z-10 bg-bg/90 backdrop-blur border-b border-line px-5 sm:px-8 py-4 flex items-start gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <VerdictBadge verdict={t.verdict} strength={t.strength} />
            {t.previous_verdict && t.previous_verdict !== t.verdict && (
              <span className="text-[12px] text-faint">{tr("brief.previously", { verdict: tr(`verdict.${t.previous_verdict}`).toLowerCase() })}</span>
            )}
          </div>
          <h2 className="text-[20px] font-medium text-ink leading-tight">{t.name}</h2>
          {t.description && <p className="text-[13px] text-muted mt-1">{t.description}</p>}
          {onAsk && (
            <button
              onClick={() => onAsk(t)}
              className="mt-3 h-8 px-3 rounded-[10px] border border-line-strong bg-surface text-[13px] font-medium text-ink inline-flex items-center gap-2 hover:bg-surface-2 transition-colors duration-150 ease-out"
            >
              <MessageSquare size={14} strokeWidth={1.5} className="text-muted" />
              {tr("brief.askAbout")}
            </button>
          )}
        </div>
        {onClose && (
          <button onClick={onClose} className="shrink-0 w-8 h-8 rounded-[10px] hover:bg-surface-2 flex items-center justify-center text-muted hover:text-ink transition-colors duration-150 ease-out" aria-label={tr("common.close")}>
            <X size={16} strokeWidth={1.5} />
          </button>
        )}
      </header>

      <div className="px-5 sm:px-8 pt-6 flex flex-col gap-8">
        {t.summary && <p className="text-[15px] leading-relaxed text-ink">{t.summary}</p>}

        <section className="rounded-2xl bg-surface border border-line p-5">
          <div className="flex items-baseline justify-between mb-3">
            <h3 className="text-[15px] font-medium text-ink">{tr("brief.trend")}</h3>
            <span className="reading text-[12px] text-faint">
              {fmtDate(t.series[0]?.date)} – {fmtDate(t.series[t.series.length - 1]?.date)}
            </span>
          </div>
          <Sparkline series={t.series} volume={t.volume} verdict={t.verdict} height={110} showAxis />
          <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2 mt-4 text-[12px]">
            <Metric label={tr("brief.coverage", { pct: "" }).trim()} value={fmtPct(m.coverage_change_pct)} hint={tr("brief.coverageVs")} color={pctColor(m.coverage_change_pct)} />
            <Metric label={tr("brief.allSources")} value={String(m.source_count)} hint={tr("brief.items", { count: m.evidence_count })} />
            <Metric label={tr("brief.teamFile")} value={String(m.upload_count)} hint={tr("brief.fromFiles", { count: m.upload_count })} />
            <Metric label="Score" value={`${t.score > 0 ? "+" : t.score < 0 ? "−" : ""}${Math.abs(t.score).toFixed(2)}`} hint="−1 … +1" color={verdictVar(t.verdict)} />
          </dl>
          {(t.reasons.includes("held_by_hysteresis") || t.reasons.includes("flip_damped") || t.verdict === "insufficient" || t.capped_days.length > 0) && (
            <ul className="mt-3 text-[12px] text-muted space-y-1">
              {t.reasons.includes("held_by_hysteresis") && <li>• {tr("brief.heldBy")}</li>}
              {t.reasons.includes("flip_damped") && <li>• {tr("brief.flipDamped")}</li>}
              {t.verdict === "insufficient" && <li>• {tr("brief.insufficientWhy")}</li>}
              {t.capped_days.length > 0 && <li>• {tr("landing.how.capped")}: {t.capped_days.map((d) => fmtDate(d)).join(", ")}</li>}
            </ul>
          )}
        </section>

        <section>
          <h3 className="text-[15px] font-medium text-ink mb-3">{tr("brief.why")}</h3>
          <ol className="flex flex-col gap-3">
            {t.points.map((p, i) => (
              <li key={i} className="flex gap-3">
                <span className="mt-[7px] w-1.5 h-1.5 rounded-full shrink-0" style={{ background: verdictVar(t.verdict) }} />
                <p className="text-[14px] leading-relaxed text-ink">
                  {p.text}{" "}
                  {p.sources.map((sid) =>
                    num.has(sid) ? (
                      <button
                        key={sid}
                        onClick={() => jump(sid)}
                        className="reading inline-flex items-center justify-center min-w-[20px] h-[18px] px-1 mx-0.5 rounded-[5px] bg-surface-2 border border-line text-muted text-[12px] align-[2px] hover:text-ink hover:border-line-strong transition-colors duration-150 ease-out"
                        title={ev[sid]?.title}
                      >
                        {num.get(sid)}
                      </button>
                    ) : null,
                  )}
                </p>
              </li>
            ))}
          </ol>
          {!t.validated && <p className="text-[12px] text-faint mt-2">{tr("brief.templateText")}</p>}
          {t.watch && (
            <div className="mt-4 rounded-xl border border-dashed border-line-strong px-4 py-3">
              <div className="text-[13px] text-muted mb-1">{tr("brief.watch")}</div>
              <p className="text-[14px] text-ink">{t.watch}</p>
            </div>
          )}
        </section>

        {t.companies.length > 0 && <Companies companies={t.companies} onCompany={links?.onCompany} />}

        <section>
          <h3 className="text-[15px] font-medium text-ink mb-3">
            {tr("brief.allSources")} <span className="reading text-[12px] text-faint font-normal">{sources.length}</span>
          </h3>
          <ol ref={listRef} className="flex flex-col gap-2">
            {sources.map((s) => (
              <SourceRow key={s.id} s={s} n={num.get(s.id)!} flash={flash === s.id} links={links} />
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}

function Metric({ label, value, hint, color }: { label: string; value: string; hint?: string; color?: string }) {
  return (
    <div className="rounded-[10px] bg-surface-2 px-3 py-2">
      <dt className="text-[12px] text-muted truncate">{label}</dt>
      <dd className="reading mt-0.5 text-[18px] leading-tight" style={{ color: color ?? "var(--ink)" }}>{value}</dd>
      {hint && <dd className="text-[12px] text-faint truncate">{hint}</dd>}
    </div>
  );
}

function SourceRow({ s, n, flash, links }: { s: Evidence; n: number; flash: boolean; links?: BriefLinks }) {
  const { t } = useTranslation();
  const isFile = s.source_type === "upload";
  const href = isFile ? (s.file_id && links?.fileHref ? links.fileHref(s.file_id) : null) : s.url;
  return (
    <li
      data-ev={s.id}
      className={`rounded-xl border px-4 py-3 transition-colors duration-[400ms] ease-out ${flash ? "border-accent bg-accent-soft" : "border-line bg-surface"}`}
    >
      <div className="flex gap-3">
        <span className="reading shrink-0 w-6 h-6 rounded-md bg-surface-2 text-[12px] text-muted flex items-center justify-center">{n}</span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap text-[12px] text-faint mb-0.5">
            {isFile ? (
              <span className="inline-flex items-center gap-1 text-ink font-medium">
                <FileIcon size={14} /> {t("brief.teamFile")}
              </span>
            ) : (
              <span className="font-medium text-muted">{s.source || domainOf(s.url)}</span>
            )}
            <span className="reading">{fmtDate(s.date)}</span>
            <SignalPill signal={s.signal} />
            {s.also > 0 && <span>{t("brief.alsoCovered", { count: s.also })}</span>}
          </div>
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer" className="text-[14px] font-medium text-ink hover:text-accent leading-snug inline-flex gap-1 items-baseline">
              <span>{isFile ? s.file_name ?? s.title : s.title}</span>
              <LinkIcon className="shrink-0 text-faint self-center" />
            </a>
          ) : (
            <span className="text-[14px] font-medium text-ink leading-snug">{isFile ? s.file_name ?? s.title : s.title}</span>
          )}
          {s.quote && s.quote !== s.title && (
            <blockquote className="mt-2 text-[13px] text-muted border-l-2 border-line-strong pl-3">“{s.quote}”</blockquote>
          )}
          {s.note && <p className="mt-1 text-[12px] text-faint">{s.note}</p>}
          {s.hn_url && s.hn_url !== s.url && (
            <a href={s.hn_url} target="_blank" rel="noopener noreferrer" className="mt-1 inline-flex items-center gap-0.5 text-[12px] text-faint hover:text-ink transition-colors duration-150 ease-out">
              {t("brief.hnDiscussion")} <LinkIcon size={12} />
            </a>
          )}
        </div>
      </div>
    </li>
  );
}

function Companies({ companies, onCompany }: { companies: CompanyRef[]; onCompany?: (id: string) => void }) {
  const { t } = useTranslation();
  return (
    <section>
      <h3 className="text-[15px] font-medium text-ink mb-3">{t("brief.companies")}</h3>
      <ul className="grid sm:grid-cols-2 gap-x-2 gap-y-2">
        {companies.map((c) => {
          const e = c.events[0];
          const aka = c.aliases.filter((a) => a.toLowerCase() !== c.name.toLowerCase());
          const Tag = onCompany ? "button" : "div";
          return (
            <li key={c.id} className="grid grid-rows-subgrid row-span-3 gap-0">
              <Tag
                {...(onCompany ? { type: "button" as const, onClick: () => onCompany(c.id) } : {})}
                className={`w-full text-left rounded-xl border border-line bg-surface px-4 py-3 grid grid-rows-subgrid row-span-3 gap-0 content-start ${onCompany ? "hover:border-line-strong cursor-pointer transition-colors duration-150 ease-out" : ""}`}
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="font-medium text-[14px] text-ink truncate">{c.name}</span>
                  <span className="text-[12px] text-faint shrink-0">{t("brief.mentions", { count: c.events.length })}</span>
                </div>
                {e && (
                  <p className="text-[12px] text-muted mt-1 line-clamp-2">
                    <span className="reading text-faint">{fmtDate(e.date)}</span> · {e.event || e.title}
                  </p>
                )}
                {aka.length > 0 && <p className="text-[12px] text-faint mt-2 truncate">{t("brief.aka", { names: aka.join(", ") })}</p>}
              </Tag>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
