import { ArrowUpRight, FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { Strength, Verdict } from "../lib/types";

export const VERDICT_ORDER: Record<Verdict, number> = { rising: 0, steady: 1, fading: 2, insufficient: 3 };

export const verdictVar = (v: Verdict) => `var(--${v})`;
export const verdictSoftVar = (v: Verdict) => `var(--${v}-soft)`;

/** A change is coloured by its own sign, never by the topic's verdict. */
export function pctColor(p: number | null | undefined) {
  if (p == null || Math.abs(p) < 0.5) return "var(--muted)";
  return p > 0 ? "var(--rising)" : "var(--fading)";
}

/**
 * The verdict mark: a wind-vane arrow (rising up-right, fading down-right),
 * a level dash for steady, or a dashed ring when there isn't enough to go on. Tellwind's
 * one signature detail; always drawn in a fixed square box so columns align.
 */
export function VerdictIcon({ verdict, size = 16 }: { verdict: Verdict; size?: number }) {
  const c = verdictVar(verdict);
  const common = {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    "aria-hidden": true,
    className: "shrink-0",
    fill: "none",
    stroke: c,
    strokeWidth: 1.75,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  } as const;
  if (verdict === "rising")
    return (
      <svg {...common}>
        <path d="M4 12 L12 4 M6.5 4 H12 V9.5" />
      </svg>
    );
  if (verdict === "fading")
    return (
      <svg {...common}>
        <path d="M4 4 L12 12 M12 6.5 V12 H6.5" />
      </svg>
    );
  if (verdict === "steady")
    return (
      <svg {...common}>
        <path d="M3 8 H13" />
      </svg>
    );
  return (
    <svg {...common}>
      <circle cx="8" cy="8" r="5" strokeDasharray="2.4 2.2" strokeWidth={1.5} />
    </svg>
  );
}

export function VerdictBadge({
  verdict,
  strength,
  size = "md",
}: {
  verdict: Verdict;
  strength?: Strength;
  size?: "sm" | "md" | "lg";
}) {
  const { t } = useTranslation();
  const label = verdict === "insufficient" && size === "sm" ? t("verdict.insufficientShort") : t(`verdict.${verdict}`);
  const pad = size === "lg" ? "h-8 px-2.5 text-[14px] gap-2" : size === "sm" ? "h-6 px-2 text-[12px] gap-1.5" : "h-7 px-2 text-[13px] gap-1.5";
  return (
    <span
      className={`inline-flex items-center rounded-md font-medium whitespace-nowrap ${pad}`}
      style={{ background: verdictSoftVar(verdict), color: verdictVar(verdict) }}
    >
      <VerdictIcon verdict={verdict} size={size === "lg" ? 16 : 14} />
      <span style={{ color: verdict === "steady" || verdict === "insufficient" ? "var(--muted)" : undefined }}>{label}</span>
      {strength && strength !== "none" && verdict !== "steady" && verdict !== "insufficient" && (
        <StrengthMeter strength={strength} verdict={verdict} />
      )}
    </span>
  );
}

export function StrengthMeter({ strength, verdict }: { strength: Strength; verdict: Verdict }) {
  const { t } = useTranslation();
  const n = strength === "strong" ? 3 : strength === "moderate" ? 2 : strength === "weak" ? 1 : 0;
  return (
    <span className="inline-flex items-end gap-[2px] ml-0.5" title={t(`strength.${strength}`)} aria-label={t(`strength.${strength}`)}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="w-[3px] rounded-[1px]"
          style={{
            height: 5 + i * 3,
            background: i < n ? verdictVar(verdict) : "color-mix(in srgb, currentColor 22%, transparent)",
          }}
        />
      ))}
    </span>
  );
}

export function SignalPill({ signal }: { signal: number }) {
  const { t } = useTranslation();
  const v: Verdict = signal > 0 ? "rising" : signal < 0 ? "fading" : "steady";
  return (
    <span
      className="inline-flex items-center gap-1 rounded-md px-1.5 h-6 text-[12px] font-medium whitespace-nowrap"
      style={{ background: verdictSoftVar(v), color: v === "steady" ? "var(--muted)" : verdictVar(v) }}
      title={t(`brief.signal.${signal}`)}
    >
      <VerdictIcon verdict={v} size={12} />
      {t(`brief.signal.${signal}`)}
    </span>
  );
}

export function FileIcon({ className = "", size = 16 }: { className?: string; size?: number }) {
  return <FileText size={size} strokeWidth={1.5} className={`shrink-0 ${className}`} aria-hidden />;
}

export function LinkIcon({ className = "", size = 14 }: { className?: string; size?: number }) {
  return <ArrowUpRight size={size} strokeWidth={1.5} className={`shrink-0 ${className}`} aria-hidden />;
}
