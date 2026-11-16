import { motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { fmtPct } from "../lib/format";
import type { TopicBrief } from "../lib/types";
import { Sparkline } from "./Sparkline";
import { FileIcon, VerdictBadge, pctColor, verdictVar } from "./bits";

interface Props {
  topic: TopicBrief;
  onOpen?: () => void;
  animate?: boolean;
  delay?: number;
  compact?: boolean;
  /** In a grid row: share row lines with the neighbours so titles, summaries, charts and figures line up. */
  subgrid?: boolean;
}

export function TopicCard({ topic: t, onOpen, animate = false, delay = 0, compact = false, subgrid = false }: Props) {
  const { t: tr } = useTranslation();
  const m = t.metrics;
  const changed = t.previous_verdict && t.previous_verdict !== t.verdict;
  const insufficient = t.verdict === "insufficient";
  const Wrapper = onOpen ? motion.button : motion.div;
  return (
    <Wrapper
      type={onOpen ? "button" : undefined}
      onClick={onOpen}
      layout={animate ? "position" : undefined}
      initial={animate ? { opacity: 0, y: 8 } : false}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={`group relative text-left w-full rounded-2xl bg-surface border border-line shadow-card overflow-hidden gap-3 ${compact ? "p-4" : "p-5"} ${subgrid ? "grid grid-rows-subgrid row-span-4" : "flex flex-col"} ${
        onOpen ? "cursor-pointer hover:border-line-strong transition-colors duration-200 ease-out" : ""
      } ${insufficient ? "hatch" : ""}`}
    >
      <div className="flex items-start justify-between gap-3">
        <h3 className={`font-medium leading-snug text-ink ${compact ? "text-[14px]" : "text-[15px]"}`}>{t.name}</h3>
        <VerdictBadge verdict={t.verdict} strength={t.strength} size="sm" />
      </div>

      {/* the call in words sits with the title; the figures below caption the chart */}
      {!compact && <p className="text-[13px] leading-relaxed text-ink/80 line-clamp-2">{t.summary}</p>}

      <Sparkline series={t.series} verdict={t.verdict} height={compact ? 40 : 52} animate={animate} delay={delay + 0.15} />

      <div className="flex items-center gap-x-3 gap-y-1 flex-wrap text-[12px] text-muted pt-3 border-t border-line">
        {!insufficient && (
          <span>
            <span className="reading" style={{ color: pctColor(m.coverage_change_pct) }}>
              {fmtPct(m.coverage_change_pct)}
            </span>{" "}
            <span className="text-faint">{tr("brief.coverageVs")}</span>
          </span>
        )}
        <span>{tr("brief.sources", { count: m.source_count })}</span>
        {m.upload_count > 0 && (
          <span className="inline-flex items-center gap-1">
            <FileIcon size={12} className="text-faint" />
            {tr("brief.fromFiles", { count: m.upload_count })}
          </span>
        )}
        {changed && (
          <span className="inline-flex items-center gap-1.5 text-faint">
            <span className="w-1.5 h-1.5 rounded-full" style={{ background: verdictVar(t.previous_verdict!) }} />
            {tr("brief.previously", { verdict: tr(`verdict.${t.previous_verdict}`).toLowerCase() })}
          </span>
        )}
      </div>

    </Wrapper>
  );
}
