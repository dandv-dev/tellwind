import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { fmtDate, fmtLongDay } from "../lib/format";
import type { Verdict } from "../lib/types";
import { verdictVar } from "./bits";

export interface BriefDay {
  date: string;
  tally: Partial<Record<Verdict, number>>;
  /** How many calls changed against the day before. */
  changes: number;
}

const ORDER: Verdict[] = ["rising", "steady", "fading", "insufficient"];

/**
 * The last weeks of briefs as a strip of days. Each day shows its mix of calls
 * and a dot when something changed, so picking a day is also reading the history.
 */
export function DayStrip({ days, current, onPick }: { days: BriefDay[]; current: string; onPick: (date: string) => void }) {
  const { t } = useTranslation();
  const ref = useRef<HTMLOListElement>(null);
  const list = [...days].sort((a, b) => a.date.localeCompare(b.date));
  const latest = list[list.length - 1]?.date;

  // Keep the chosen day in view (the newest one on first load).
  useEffect(() => {
    const el = ref.current?.querySelector<HTMLElement>(`[data-day="${current}"]`);
    el?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }, [current]);

  return (
    <nav aria-label={t("brief.pickDate")} className="-mx-4 sm:mx-0">
      <ol ref={ref} className="flex gap-1 overflow-x-auto scrollbar-none px-4 sm:px-0 pb-1 snap-x">
        {list.map((d, i) => {
          const sel = d.date === current;
          const tally = d.tally ?? {};
          const total = ORDER.reduce((a, v) => a + (tally[v] ?? 0), 0) || 1;
          const newMonth = i === 0 || d.date.slice(0, 7) !== list[i - 1].date.slice(0, 7);
          return (
            <li key={d.date} className="snap-start shrink-0">
              <button
                data-day={d.date}
                onClick={() => onPick(d.date)}
                aria-current={sel ? "date" : undefined}
                aria-label={`${fmtLongDay(d.date)}${d.date === latest ? ` · ${t("brief.latest")}` : ""}`}
                title={fmtLongDay(d.date)}
                className={`w-12 rounded-[10px] border pt-1.5 pb-2 flex flex-col items-center gap-1 transition-colors duration-150 ease-out ${
                  sel ? "bg-surface border-line-strong shadow-card" : "border-transparent hover:bg-surface-2"
                }`}
              >
                <span className={`text-[12px] leading-4 ${sel ? "text-ink" : "text-faint"}`}>
                  {newMonth ? fmtDate(d.date, { month: "short" }).replace(".", "") : fmtDate(d.date, { weekday: "short" }).replace(".", "")}
                </span>
                <span className={`reading text-[15px] leading-5 ${sel ? "text-ink font-medium" : "text-muted"}`}>{fmtDate(d.date, { day: "numeric" })}</span>
                <span className="w-8 h-1 rounded-full overflow-hidden flex bg-surface-2" aria-hidden>
                  {ORDER.map((v) =>
                    tally[v] ? (
                      <span
                        key={v}
                        className={v === "insufficient" ? "hatch" : ""}
                        style={{ width: `${((tally[v] ?? 0) / total) * 100}%`, background: v === "insufficient" ? undefined : verdictVar(v), opacity: v === "steady" ? 0.55 : 1 }}
                      />
                    ) : null,
                  )}
                </span>
                <span
                  aria-hidden
                  className={`w-1 h-1 rounded-full ${d.changes ? (sel ? "bg-ink" : "bg-muted") : "bg-transparent"}`}
                  title={d.changes ? t("brief.changesOn", { count: d.changes }) : undefined}
                />
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
