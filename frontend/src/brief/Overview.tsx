import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { fmtPct } from "../lib/format";
import type { TopicBrief, Verdict } from "../lib/types";
import { VERDICT_ORDER, VerdictIcon, pctColor, verdictVar } from "./bits";

const ENTER = 0.22;
const WEEK = 7;

interface Props {
  topics: TopicBrief[];
  onOpen?: (id: string) => void;
  animate?: boolean;
  delay?: number;
}

/** Score a week ago, from the topic's daily momentum series (its last point is today). */
function weekAgo(x: TopicBrief): number | null {
  const s = x.series ?? [];
  if (s.length < 2) return null;
  return s[Math.max(0, s.length - 1 - WEEK)].score;
}

const signed = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v).toFixed(2)}`;

/*
 * Columns follow the width of the card itself (container queries), so the same
 * component works full width in the app and inside the narrow landing demo.
 *   narrow: name, score, 7-day change; the scale gets its own line below
 *   @lg:    name, scale, score, 7-day change
 *   @3xl:   plus coverage against the prior weeks and the number of sources
 */
const GRID =
  "grid grid-cols-[minmax(0,1fr)_52px_52px] @lg:grid-cols-[minmax(0,30%)_minmax(0,1fr)_52px_52px] @3xl:grid-cols-[minmax(0,24%)_minmax(0,1fr)_56px_56px_64px_56px] gap-x-3 @3xl:gap-x-4";
const C_NAME = "col-start-1 row-start-1";
const C_SCALE = "col-span-3 row-start-2 @lg:col-span-1 @lg:col-start-2 @lg:row-start-1";
const C_SCORE = "col-start-2 row-start-1 @lg:col-start-3";
const C_WEEK = "col-start-3 row-start-1 @lg:col-start-4";
const C_COV = "hidden @3xl:block @3xl:col-start-5 @3xl:row-start-1";
const C_SRC = "hidden @3xl:block @3xl:col-start-6 @3xl:row-start-1";

/**
 * Every topic on one momentum scale, ranked. Each row shows where the topic is
 * today (filled dot) and where it was a week ago (hollow dot), so the direction
 * of travel reads at a glance, with the figures behind it on the right.
 */
export function Overview({ topics, onOpen, animate = false, delay = 0 }: Props) {
  const { t } = useTranslation();
  const rows = [...topics].sort((a, b) => {
    const ai = a.verdict === "insufficient" ? 1 : 0;
    const bi = b.verdict === "insufficient" ? 1 : 0;
    return ai - bi || b.score - a.score;
  });
  const reach = Math.max(0.5, ...topics.flatMap((x) => [Math.abs(x.score), Math.abs(weekAgo(x) ?? 0)]));
  const scale = reach * 1.08;
  const pos = (v: number) => 50 + (v / scale) * 50;

  const tally = (["rising", "steady", "fading", "insufficient"] as Verdict[])
    .map((v) => ({ v, n: topics.filter((x) => x.verdict === v).length }))
    .filter((x) => x.n > 0)
    .sort((a, b) => VERDICT_ORDER[a.v] - VERDICT_ORDER[b.v]);

  const thresholds = (
    <>
      <span className="absolute -translate-x-full pr-1.5 whitespace-nowrap" style={{ left: `${pos(-ENTER)}%` }}>
        ← {t("verdict.fading").toLowerCase()}
      </span>
      <span className="absolute pl-1.5 whitespace-nowrap" style={{ left: `${pos(ENTER)}%` }}>
        {t("verdict.rising").toLowerCase()} →
      </span>
    </>
  );

  return (
    <div className="@container rounded-2xl bg-surface border border-line shadow-card p-4 sm:p-6">
      <div className="flex items-start justify-between gap-x-6 gap-y-2 flex-wrap mb-4">
        <div className="min-w-0">
          <h2 className="text-[18px] font-medium text-ink">{t("brief.overview")}</h2>
          <p className="text-[13px] text-muted mt-1">{t("brief.overviewHint")}</p>
        </div>
        <ul className="flex gap-x-4 gap-y-1 flex-wrap text-[13px] text-muted pt-1">
          {tally.map(({ v, n }) => (
            <li key={v} className="inline-flex items-center gap-1.5 whitespace-nowrap">
              <VerdictIcon verdict={v} size={14} />
              <span className="reading text-ink">{n}</span>
              {t(`verdict.${v === "insufficient" ? "insufficientShort" : v}`).toLowerCase()}
            </li>
          ))}
        </ul>
      </div>

      {/* column heads; on narrow cards only the figures get a head */}
      <div className={`${GRID} px-2 pb-2 border-b border-line text-[12px] text-faint items-end`}>
        <span className={`${C_NAME} hidden @lg:block`}>{t("brief.colTopic")}</span>
        <span className={`${C_SCALE} hidden @lg:block relative h-4`}>{thresholds}</span>
        <span className={`${C_SCORE} text-right`}>{t("brief.colScore")}</span>
        <span className={`${C_WEEK} text-right`} title={t("brief.colWeekHint")}>{t("brief.colWeek")}</span>
        <span className={`${C_COV} text-right`} title={t("brief.colCoverageHint")}>{t("brief.colCoverage")}</span>
        <span className={`${C_SRC} text-right`}>{t("brief.colSources")}</span>
      </div>

      <ol className="flex flex-col pt-1">
        {rows.map((r, i) => {
          const ins = r.verdict === "insufficient";
          const prev = ins ? null : weekAgo(r);
          const d = prev == null ? null : r.score - prev;
          const changed = r.previous_verdict && r.previous_verdict !== r.verdict;
          const color = verdictVar(r.verdict);
          const Row = onOpen ? "button" : "div";
          return (
            <li key={r.id}>
              <Row
                {...(onOpen ? { type: "button" as const, onClick: () => onOpen(r.id) } : {})}
                className={`w-full ${GRID} items-center rounded-lg px-2 pt-2 pb-1 @lg:py-0 text-left ${onOpen ? "hover:bg-surface-2 cursor-pointer transition-colors duration-150 ease-out" : ""}`}
              >
                <span className={`${C_NAME} flex items-center gap-2 min-w-0 @lg:h-10`}>
                  <span className="w-4 h-4 shrink-0 flex items-center justify-center">
                    <VerdictIcon verdict={r.verdict} size={14} />
                  </span>
                  <span className="truncate text-[13px] text-ink">{r.name}</span>
                  {changed && (
                    <span className="hidden @md:inline shrink-0 text-[12px] text-faint whitespace-nowrap">
                      {t("brief.previously", { verdict: t(`verdict.${r.previous_verdict === "insufficient" ? "insufficientShort" : r.previous_verdict}`).toLowerCase() })}
                    </span>
                  )}
                </span>

                <span className={`${C_SCALE} relative h-7 @lg:h-10`}>
                  <Zones pos={pos} />
                  {ins ? (
                    <span className="absolute inset-y-[6px] @lg:inset-y-[10px] left-[30%] right-[30%] rounded hatch border border-dashed border-line-strong flex items-center justify-center text-[12px] text-faint whitespace-nowrap overflow-hidden">
                      {t("verdict.insufficientShort")}
                    </span>
                  ) : (
                    <>
                      {prev != null && (
                        <>
                          <motion.span
                            aria-hidden
                            className="absolute top-1/2 -translate-y-1/2 h-[2px] rounded-full"
                            style={{
                              left: `${Math.min(pos(prev), pos(r.score))}%`,
                              width: `${Math.abs(pos(r.score) - pos(prev))}%`,
                              background: color,
                            }}
                            initial={animate ? { opacity: 0 } : false}
                            animate={{ opacity: r.verdict === "steady" ? 0.35 : 0.5 }}
                            transition={{ delay: delay + i * 0.05 + 0.3, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
                          />
                          <span
                            aria-hidden
                            className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border-[1.5px] border-faint bg-surface"
                            style={{ left: `${pos(prev)}%` }}
                          />
                        </>
                      )}
                      <motion.span
                        aria-hidden
                        className="absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-3 h-3 rounded-full ring-2 ring-surface"
                        style={{ background: color }}
                        initial={animate ? { left: `${pos(prev ?? 0)}%` } : false}
                        animate={{ left: `${pos(r.score)}%` }}
                        transition={{ delay: delay + i * 0.05, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
                      />
                    </>
                  )}
                </span>

                <span className={`${C_SCORE} reading text-right text-[12px]`} style={{ color: ins ? "var(--faint)" : color }}>
                  {ins ? "—" : signed(r.score)}
                </span>
                <span className={`${C_WEEK} reading text-right text-[12px] ${d != null && Math.abs(d) >= 0.05 ? "text-ink" : "text-faint"}`}>
                  {d == null ? "—" : signed(d)}
                </span>
                <span className={`${C_COV} reading text-right text-[12px]`} style={{ color: ins ? "var(--faint)" : pctColor(r.metrics.coverage_change_pct) }}>
                  {ins ? "—" : fmtPct(r.metrics.coverage_change_pct)}
                </span>
                <span className={`${C_SRC} reading text-right text-[12px] text-muted`}>{r.metrics.source_count}</span>
              </Row>
            </li>
          );
        })}
      </ol>

      <div className="mt-3 px-2 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[12px] text-faint">
        <span className="inline-flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full border-[1.5px] border-faint" />
          {t("brief.weekAgo")}
          <span className="w-4 h-[2px] rounded-full bg-line-strong" />
          <span className="w-3 h-3 rounded-full bg-muted" />
          {t("common.today")}
        </span>
        {/* on narrow cards the threshold labels sit here instead of in the head */}
        <span className="@lg:hidden relative h-4 flex-1 min-w-[200px]">{thresholds}</span>
      </div>
    </div>
  );
}

/**
 * Zero line, the two call thresholds and a faint tint past them, drawn per row so
 * they join into bands down the list (the tint only when rows are one line high).
 */
function Zones({ pos }: { pos: (v: number) => number }) {
  return (
    <span aria-hidden className="absolute inset-0 pointer-events-none">
      <span className="hidden @lg:block absolute inset-y-0 left-0" style={{ width: `${pos(-ENTER)}%`, background: "color-mix(in srgb, var(--fading) 6%, transparent)" }} />
      <span className="hidden @lg:block absolute inset-y-0 right-0" style={{ left: `${pos(ENTER)}%`, background: "color-mix(in srgb, var(--rising) 6%, transparent)" }} />
      <span className="absolute inset-y-0 w-px bg-line-strong" style={{ left: "50%" }} />
      <span className="absolute inset-y-0 border-l border-dashed" style={{ left: `${pos(ENTER)}%`, borderColor: "color-mix(in srgb, var(--rising) 40%, transparent)" }} />
      <span className="absolute inset-y-0 border-l border-dashed" style={{ left: `${pos(-ENTER)}%`, borderColor: "color-mix(in srgb, var(--fading) 40%, transparent)" }} />
    </span>
  );
}
