import { useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { fmtCost, fmtDate, fmtDateTime, fmtLongDay } from "../lib/format";
import type { Brief, BriefLinks, TopicBrief } from "../lib/types";
import { DayStrip, type BriefDay } from "./DayStrip";
import { Overview } from "./Overview";
import { TopicCard } from "./TopicCard";
import { TopicDrawer } from "./TopicDetail";
import { VERDICT_ORDER, VerdictIcon, verdictVar } from "./bits";

export interface BriefNav {
  days: BriefDay[];
  onPick: (date: string) => void;
  /** Shown when this is not the latest brief. */
  onLatest?: () => void;
}

interface Props {
  brief: Brief;
  links?: BriefLinks;
  /** Picking another day: a strip of the last weeks under the title. */
  nav?: BriefNav;
  /** Quiet links after the meta line (download, trace). */
  actions?: ReactNode;
  /** Shown in the topic panel when set: "ask about this topic". */
  onAskTopic?: (topic: TopicBrief) => void;
  initialTopic?: string | null;
}

/**
 * The brief reads top to bottom like a morning report: the day and what changed,
 * every topic on one scale, then the topics that are moving before the ones that hold.
 */
export function BriefView({ brief, links, nav, actions, onAskTopic, initialTopic = null }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState<string | null>(initialTopic);
  const topic = brief.topics.find((x) => x.id === open) ?? null;

  const { moving, steady, unclear } = useMemo(() => {
    const by = (v: string) => brief.topics.filter((x) => x.verdict === v);
    return {
      moving: [...by("rising").sort((a, b) => b.score - a.score), ...by("fading").sort((a, b) => a.score - b.score)],
      steady: by("steady").sort((a, b) => b.score - a.score),
      unclear: by("insufficient"),
    };
  }, [brief]);

  const groups = [
    { key: "moving", title: t("brief.moving"), items: moving, cols: "sm:grid-cols-2" },
    { key: "steady", title: t("brief.holding"), items: steady, cols: "grid-cols-[repeat(auto-fill,minmax(min(100%,300px),1fr))]" },
    { key: "unclear", title: t("verdict.insufficient"), items: unclear, cols: "grid-cols-[repeat(auto-fill,minmax(min(100%,300px),1fr))]" },
  ].filter((g) => g.items.length);

  return (
    <div className="flex flex-col gap-8 sm:gap-10">
      <header className="flex flex-col gap-6">
        <div className="min-w-0">
          <p className="text-[13px] text-muted flex flex-wrap items-baseline gap-x-2">
            {brief.workspace.subject}
            {nav?.onLatest && (
              <button onClick={nav.onLatest} className="text-ink font-medium hover:underline underline-offset-4 decoration-line-strong">
                {t("brief.toLatest")} →
              </button>
            )}
          </p>
          <h1 className={`mt-1 ${titleCls}`}>{fmtLongDay(brief.date)}</h1>
          <BriefMeta brief={brief} actions={actions} />
        </div>
        {nav && nav.days.length > 1 && <DayStrip days={nav.days} current={brief.date} onPick={nav.onPick} />}
        <ChangeLine brief={brief} onOpen={setOpen} bare />
      </header>

      <Overview topics={brief.topics} onOpen={setOpen} />

      {groups.map((g) => (
        <section key={g.key} aria-label={g.title}>
          <h2 className="flex items-baseline gap-2 text-[18px] font-medium text-ink mb-4">
            {g.title} <span className="reading text-[12px] text-faint font-normal">{g.items.length}</span>
          </h2>
          <div className={`grid gap-4 ${g.cols}`}>
            {g.items.map((x) => (
              <TopicCard key={x.id} topic={x} onOpen={() => setOpen(x.id)} subgrid />
            ))}
          </div>
        </section>
      ))}

      <details id="method" className="text-[13px] text-muted rounded-2xl border border-line px-5 py-4 bg-surface">
        <summary className="cursor-pointer font-medium text-ink">{t("brief.method")}</summary>
        <p className="mt-2 leading-relaxed max-w-3xl">{t("brief.methodText")}</p>
      </details>

      <TopicDrawer brief={brief} topic={topic} onClose={() => setOpen(null)} links={links} onAsk={onAskTopic} />
    </div>
  );
}

const titleCls = "text-[28px] sm:text-[32px] font-medium text-ink leading-tight tracking-[-0.02em]";
/** When the brief was made, how fresh its news is and what it cost, then the file links. */
function BriefMeta({ brief, actions }: { brief: Brief; actions?: ReactNode }) {
  const { t } = useTranslation();
  const parts = [
    t("brief.generated", { when: fmtDateTime(brief.generated_at) }),
    brief.data_through ? t("brief.dataThrough", { date: fmtDate(brief.data_through) }) : null,
    brief.cost_usd != null ? t("brief.cost", { cost: fmtCost(brief.cost_usd) }) : null,
  ].filter(Boolean);
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="text-[12px] text-faint tabular-nums flex flex-wrap gap-x-3 gap-y-1">
        {parts.map((p, i) => (
          <span key={i}>{p}</span>
        ))}
      </p>
      {actions && (
        <>
          <span aria-hidden className="hidden sm:block w-px h-3 bg-line-strong" />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">{actions}</div>
        </>
      )}
    </div>
  );
}

export function ChangeLine({ brief, onOpen, bare = false }: { brief: Brief; onOpen?: (id: string) => void; bare?: boolean }) {
  const { t } = useTranslation();
  const label = brief.previous_date ? t("brief.changedSince", { date: fmtDate(brief.previous_date) }) : t("brief.firstBrief");
  return (
    <div className={bare ? "flex flex-col gap-3" : "rounded-2xl border border-line bg-surface p-4 sm:px-5 flex flex-col gap-3 shadow-card"}>
      {bare ? (
        <div className="flex flex-col gap-1.5 max-w-3xl">
          <span className="text-[13px] text-muted">{label}</span>
          <p className="text-[15px] sm:text-[18px] leading-snug text-ink">{brief.headline}</p>
        </div>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-start gap-2 sm:gap-3">
          <span className="shrink-0 w-fit text-[12px] text-muted bg-surface-2 rounded-md px-2 h-6 inline-flex items-center whitespace-nowrap">{label}</span>
          <p className="text-[15px] leading-snug text-ink font-medium">{brief.headline}</p>
        </div>
      )}
      {brief.changes.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {brief.changes
            .slice()
            .sort((a, b) => VERDICT_ORDER[a.to] - VERDICT_ORDER[b.to])
            .map((c) => {
              const Tag = onOpen ? "button" : "span";
              const to = c.to === "insufficient" ? "insufficientShort" : c.to;
              return (
                <Tag
                  key={c.topic_id}
                  {...(onOpen ? { type: "button" as const, onClick: () => onOpen(c.topic_id) } : {})}
                  className="inline-flex items-center gap-2 rounded-lg border border-line bg-surface px-2.5 h-8 text-[12px] hover:border-line-strong transition-colors duration-150 ease-out"
                >
                  <span className="font-medium text-ink">{c.name}</span>
                  <span className="text-faint">{t(`verdict.${c.from === "insufficient" ? "insufficientShort" : c.from}`).toLowerCase()} →</span>
                  <span className="inline-flex items-center gap-1 font-medium" style={{ color: c.to === "steady" || c.to === "insufficient" ? "var(--muted)" : verdictVar(c.to) }}>
                    <VerdictIcon verdict={c.to} size={12} />
                    {t(`verdict.${to}`).toLowerCase()}
                  </span>
                </Tag>
              );
            })}
        </div>
      )}
    </div>
  );
}
