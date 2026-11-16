import { motion } from "motion/react";
import { useId } from "react";
import type { Verdict } from "../lib/types";
import { verdictVar } from "./bits";

const ENTER = 0.22;

interface Props {
  series: { date: string; score: number }[];
  volume?: number[];
  verdict: Verdict;
  height?: number;
  /** Draw the line in (landing demo only). */
  animate?: boolean;
  delay?: number;
  showBand?: boolean;
  showAxis?: boolean;
  className?: string;
}

/** Momentum over the last three weeks: score line, steady band, faint daily volume. */
export function Sparkline({
  series,
  volume,
  verdict,
  height = 56,
  animate = false,
  delay = 0,
  showBand = true,
  showAxis = false,
  className = "",
}: Props) {
  const gid = useId().replace(/:/g, "");
  const W = 240;
  const H = height;
  const padY = 5;
  const vals = series.map((s) => s.score);
  const max = Math.max(0.45, ...vals.map((v) => Math.abs(v))) * 1.08;
  const n = Math.max(2, vals.length);
  const x = (i: number) => (i / (n - 1)) * W;
  const y = (v: number) => padY + ((max - v) / (2 * max)) * (H - 2 * padY);
  const pts = vals.map((v, i) => [x(i), y(v)] as const);
  const line = pts.map(([px, py], i) => `${i ? "L" : "M"}${px.toFixed(1)},${py.toFixed(1)}`).join(" ");
  const area = pts.length ? `${line} L${W},${y(0)} L0,${y(0)} Z` : "";
  const color = verdict === "insufficient" ? "var(--insufficient)" : verdictVar(verdict);
  const last = pts[pts.length - 1];

  // Daily volume (28 days) aligned to the right edge, behind the line.
  const vol = (volume ?? []).slice(-n);
  const vmax = Math.max(1, ...vol);

  return (
    <div className={`relative w-full ${className}`} style={{ height }}>
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="absolute inset-0 w-full h-full block overflow-visible" aria-hidden>
      <defs>
        <linearGradient id={`g${gid}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.22" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {showBand && (
        <rect x="0" width={W} y={y(ENTER)} height={y(-ENTER) - y(ENTER)} fill="var(--steady)" opacity="0.07" />
      )}
      {vol.map((v, i) => {
        const bw = W / n;
        const h = (v / vmax) * (H * 0.32);
        return <rect key={i} x={i * bw + bw * 0.2} width={bw * 0.6} y={H - h} height={h} fill="var(--faint)" opacity="0.18" rx="1" />;
      })}
      <line x1="0" x2={W} y1={y(0)} y2={y(0)} stroke="var(--line-strong)" strokeDasharray="3 3" strokeWidth="1" vectorEffect="non-scaling-stroke" />
      {showAxis && (
        <>
          <line x1="0" x2={W} y1={y(ENTER)} y2={y(ENTER)} stroke="var(--rising)" strokeOpacity="0.35" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />
          <line x1="0" x2={W} y1={y(-ENTER)} y2={y(-ENTER)} stroke="var(--fading)" strokeOpacity="0.35" strokeDasharray="2 4" vectorEffect="non-scaling-stroke" />
        </>
      )}
      {animate ? (
        <>
          <motion.path
            d={area}
            fill={`url(#g${gid})`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: delay + 0.7, duration: 0.6 }}
          />
          <motion.path
            d={line}
            fill="none"
            stroke={color}
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
            initial={{ pathLength: 0 }}
            animate={{ pathLength: 1 }}
            transition={{ delay, duration: 1.1, ease: "easeInOut" }}
          />
        </>
      ) : (
        <>
          <path d={area} fill={`url(#g${gid})`} />
          <path d={line} fill="none" stroke={color} strokeWidth="2" strokeLinejoin="round" strokeLinecap="round" vectorEffect="non-scaling-stroke" />
        </>
      )}
    </svg>
      {last && (
        <motion.span
          className="absolute w-[7px] h-[7px] -ml-[3.5px] -mt-[3.5px] rounded-full"
          style={{ left: `${(last[0] / W) * 100}%`, top: `${(last[1] / H) * 100}%`, background: color, boxShadow: "0 0 0 2px var(--surface)" }}
          initial={animate ? { scale: 0 } : false}
          animate={{ scale: 1 }}
          transition={{ delay: delay + 1.05, type: "spring", stiffness: 400, damping: 18 }}
        />
      )}
    </div>
  );
}
