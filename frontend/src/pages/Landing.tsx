import { ArrowRight, Check } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { ChangeLine } from "../brief/BriefView";
import { Overview } from "../brief/Overview";
import { TopicCard } from "../brief/TopicCard";
import { FileIcon, VerdictIcon, verdictVar } from "../brief/bits";
import { TopBar } from "../components/TopBar";
import { useMe } from "../lib/auth";
import type { Brief, Strength, TopicBrief, Verdict } from "../lib/types";

// The hero demo is built from the same components as the Brief tab, fed with
// a small hand-made brief. Nothing here talks to the API.

function wave(n: number, from: number, to: number, seed: number, wiggle = 0.05): { date: string; score: number }[] {
  const out = [];
  for (let i = 0; i < n; i++) {
    const k = i / (n - 1);
    const ease = k * k * (3 - 2 * k);
    const noise = Math.sin(i * 1.7 + seed) * wiggle + Math.sin(i * 0.6 + seed * 2) * wiggle * 0.6;
    const d = new Date(Date.UTC(2026, 9, 27 + i));
    out.push({ date: d.toISOString().slice(0, 10), score: +(from + (to - from) * ease + noise).toFixed(3) });
  }
  return out;
}

function vol(seed: number, trend: number): number[] {
  return Array.from({ length: 28 }, (_, i) => Math.max(0, 2 + trend * (i / 27) * 3 + Math.sin(i * 1.3 + seed) * 1.2 + ((i * 7 + seed) % 3)));
}

function topic(
  id: string,
  name: string,
  verdict: Verdict,
  score: number,
  strength: Strength,
  change: number | null,
  sources: number,
  opts: { prev?: Verdict; from?: number; seed?: number; uploads?: number } = {},
): TopicBrief {
  const from = opts.from ?? score * 0.2;
  return {
    id,
    name,
    description: "",
    verdict,
    previous_verdict: opts.prev ?? verdict,
    strength,
    score,
    metrics: {
      coverage_change_pct: change,
      recent_per_day: 0,
      baseline_per_day: 0,
      tone: 0,
      tone_vs_subject: 0,
      evidence_count: sources * 2,
      recent_count: sources,
      source_count: sources,
      upload_count: opts.uploads ?? 0,
      attention: 0,
    },
    series: verdict === "insufficient" ? [] : wave(21, from, score, opts.seed ?? 1),
    volume: vol(opts.seed ?? 1, score),
    summary: "",
    points: [],
    watch: "",
    validated: true,
    sources: [],
    companies: [],
    reasons: [],
    capped_days: [],
  };
}

const DEMO_TOPICS: TopicBrief[] = [
  topic("mcp", "Model Context Protocol", "rising", 0.48, "moderate", 84, 77, { prev: "steady", from: 0.05, seed: 2 }),
  topic("agents", "Coding agents", "rising", 0.36, "moderate", 41, 108, { from: 0.28, seed: 4 }),
  topic("review", "AI code review", "steady", 0.09, "weak", 6, 31, { from: 0.14, seed: 7 }),
  topic("cli", "Terminal & CLI agents", "steady", -0.04, "weak", -3, 22, { from: 0.06, seed: 3 }),
  topic("builders", "Vibe coding & app builders", "fading", -0.31, "weak", -27, 46, { prev: "steady", from: 0.02, seed: 5, uploads: 1 }),
  topic("local", "Local coding models", "insufficient", 0, "none", null, 3, { seed: 6 }),
];

const CARD_TOPICS = ["mcp", "builders", "agents", "review"].map((id) => DEMO_TOPICS.find((x) => x.id === id)!);

type Phase = 0 | 1 | 2;
const PHASE_MS: Record<Phase, number> = { 0: 2300, 1: 2200, 2: 7500 };

const SOURCE_CHIPS = [
  { label: "news.ycombinator.com", kind: "hn" },
  { label: "techcrunch.com", kind: "news" },
  { label: "MCP pilot notes.txt", kind: "file" },
  { label: "theverge.com", kind: "news" },
  { label: "infoq.com", kind: "news" },
  { label: "Developer survey Q4.pdf", kind: "file" },
  { label: "github.blog", kind: "news" },
  { label: "news.ycombinator.com", kind: "hn" },
  { label: "venturebeat.com", kind: "news" },
  { label: "App builders note.docx", kind: "file" },
  { label: "zdnet.com", kind: "news" },
  { label: "thenewstack.io", kind: "news" },
] as const;

function HeroDemo() {
  const { t } = useTranslation();
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<Phase>(reduce ? 2 : 0);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    if (reduce) return;
    const id = window.setTimeout(() => {
      if (phase === 2) {
        setPhase(0);
        setCycle((c) => c + 1);
      } else setPhase((phase + 1) as Phase);
    }, PHASE_MS[phase]);
    return () => window.clearTimeout(id);
  }, [phase, reduce]);

  const brief: Brief = useMemo(
    () => ({
      version: 1,
      workspace: { id: "demo", name: "DevTools Radar", subject: t("landing.demo.subject") },
      date: "2026-11-16",
      previous_date: "2026-11-15",
      generated_at: "2026-11-16T06:01:00Z",
      run_id: "demo",
      headline: t("landing.demo.headline"),
      changes: [
        { topic_id: "mcp", name: "Model Context Protocol", from: "steady", to: "rising" },
        { topic_id: "builders", name: "Vibe coding & app builders", from: "steady", to: "fading" },
      ],
      tally: { rising: 2, steady: 2, fading: 1, insufficient: 1 },
      topics: DEMO_TOPICS,
      evidence: {},
    }),
    [t],
  );

  const status = phase === 0 ? t("landing.demo.gathering") : phase === 1 ? t("landing.demo.weighing") : t("landing.demo.ready");

  return (
    <div className="relative">
      <div
        role="img"
        aria-label={t("landing.demo.aria")}
        className="relative rounded-[20px] border border-line bg-bg shadow-[0_24px_64px_-24px_rgb(8_14_20/0.45)] overflow-hidden"
      >
        {/* window chrome */}
        <div className="flex items-center gap-3 px-4 h-11 border-b border-line bg-surface">
          <span className="flex gap-1.5" aria-hidden>
            <span className="w-2.5 h-2.5 rounded-full bg-line-strong" />
            <span className="w-2.5 h-2.5 rounded-full bg-line-strong" />
            <span className="w-2.5 h-2.5 rounded-full bg-line-strong" />
          </span>
          <span className="text-[12px] text-faint truncate">
            DevTools Radar <span className="mx-1">/</span> <span className="text-ink font-medium">{t("brief.tab")}</span>
          </span>
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-md bg-surface-2 px-2 h-6 text-[12px] text-muted whitespace-nowrap">
            {phase < 2 ? (
              <span className={`w-1.5 h-1.5 rounded-full bg-accent ${phase === 0 ? "animate-pulse" : ""}`} />
            ) : (
              <Check size={12} strokeWidth={2} className="text-rising" aria-hidden />
            )}
            <AnimatePresence mode="wait" initial={false}>
              <motion.span key={phase} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
                {status}
              </motion.span>
            </AnimatePresence>
          </span>
        </div>

        <div className="p-3 sm:p-4 h-[600px] sm:h-[570px] overflow-hidden">
          <AnimatePresence mode="wait">
            {phase === 0 ? (
              <motion.div key={`g${cycle}`} exit={{ opacity: 0 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }} className="h-full flex flex-col">
                <Gathering />
              </motion.div>
            ) : phase === 1 ? (
              <motion.div key={`w${cycle}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0, y: -8 }} transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}>
                <Overview topics={DEMO_TOPICS} animate delay={0.1} />
              </motion.div>
            ) : (
              <motion.div key={`b${cycle}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col gap-3">
                <motion.div initial={reduce ? false : { opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}>
                  <ChangeLine brief={brief} />
                </motion.div>
                <div className="grid sm:grid-cols-2 gap-3">
                  {CARD_TOPICS.map((tp, i) => (
                    <div key={tp.id} className={i >= 2 ? "hidden sm:block" : ""}>
                      <TopicCard topic={tp} animate={!reduce} delay={0.15 + i * 0.09} compact />
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function Gathering() {
  const { t } = useTranslation();
  const [n, setN] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / 1900);
      setN(Math.round(214 * (1 - Math.pow(1 - k, 3))));
      if (k < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);
  return (
    <div className="h-full rounded-2xl border border-line bg-surface shadow-card p-5 flex flex-col">
      <div className="flex items-baseline justify-between">
        <span className="text-[13px] text-muted">{t("landing.demo.sources")}</span>
        <span className="reading text-[28px] text-ink leading-none">{n}</span>
      </div>
      <div className="mt-5 flex flex-wrap gap-2 content-start">
        {SOURCE_CHIPS.map((c, i) => (
          <motion.span
            key={i}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 + i * 0.12, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 h-8 text-[12px] ${
              c.kind === "file" ? "border-line-strong bg-surface-2 text-ink" : "border-line bg-bg text-muted"
            }`}
          >
            {c.kind === "file" ? <FileIcon size={14} className="text-muted" /> : c.kind === "hn" ? <HnMark /> : <span className="w-1.5 h-1.5 rounded-full bg-faint" />}
            {c.label}
          </motion.span>
        ))}
      </div>
      <div className="mt-auto flex flex-col gap-2">
        {[0.92, 0.7, 0.81].map((w, i) => (
          <motion.div
            key={i}
            className="h-2 rounded-full bg-surface-2 overflow-hidden"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.6 + i * 0.2 }}
          >
            <motion.div
              className="h-full rounded-full bg-line-strong"
              initial={{ width: "0%" }}
              animate={{ width: `${w * 100}%` }}
              transition={{ delay: 0.7 + i * 0.2, duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            />
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function HnMark() {
  return <span className="w-3.5 h-3.5 rounded-[3px] bg-[#ff6600] text-white text-[9px] font-medium flex items-center justify-center leading-none">Y</span>;
}

function CtaLink({ to, children, variant = "primary" }: { to: string; children: ReactNode; variant?: "primary" | "secondary" | "glass" }) {
  const cls =
    variant === "primary"
      ? "bg-accent text-accent-ink hover:brightness-110 shadow-[inset_0_1px_0_rgb(255_255_255/0.14)]"
      : variant === "glass"
        ? "bg-white/10 text-ink border border-white/20 backdrop-blur-sm hover:bg-white/15"
        : "bg-surface text-ink border border-line-strong hover:bg-surface-2";
  return (
    <Link
      to={to}
      className={`inline-flex items-center justify-center gap-2 h-12 px-5 rounded-[10px] text-[15px] font-medium whitespace-nowrap transition-[filter,background-color] duration-150 ease-out active:scale-[0.98] ${cls}`}
    >
      {children}
    </Link>
  );
}

function SectionHead({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {
  return (
    <div className="max-w-2xl">
      <div className="text-[13px] text-muted">{eyebrow}</div>
      <h2 className="mt-2 text-[28px] sm:text-[32px] leading-[1.15] font-medium text-ink tracking-[-0.02em] text-balance">{title}</h2>
      {subtitle && <p className="mt-3 text-[15px] leading-relaxed text-muted text-pretty">{subtitle}</p>}
    </div>
  );
}

export default function Landing() {
  const { t } = useTranslation();
  const { data: me } = useMe();
  const appLink = me ? "/app" : "/login?mode=signup";

  return (
    <div className="min-h-dvh overflow-x-clip bg-bg">
      {/* ------------------------------------------------ hero: the sea scene */}
      <section className="relative">
        <div className="relative">
        <div aria-hidden className="absolute inset-x-0 top-0 -bottom-[200px] sm:-bottom-[320px] overflow-hidden [mask-image:linear-gradient(to_bottom,black_calc(100%-200px),transparent)] sm:[mask-image:linear-gradient(to_bottom,black_calc(100%-320px),transparent)]">
          <img
            src="/brand/photos/visual-element.jpg"
            alt=""
            width={1500}
            height={2000}
            fetchPriority="high"
            className="w-full h-full object-cover object-[center_45%]"
          />
          <div className="absolute inset-0 bg-[linear-gradient(100deg,rgb(8_14_20/0.62)_0%,rgb(8_14_20/0.30)_45%,rgb(8_14_20/0.05)_75%)]" />
          <div className="absolute inset-x-0 top-0 h-40 bg-[linear-gradient(to_bottom,rgb(8_14_20/0.5),transparent)]" />
          <div className="sm:hidden absolute inset-0 bg-[rgb(8_14_20/0.3)]" />
        </div>

        <TopBar
          overlay
          right={
            me ? (
              <Link to="/app" className="h-9 px-4 rounded-[10px] bg-accent text-accent-ink text-[13px] font-medium hidden sm:inline-flex items-center hover:brightness-110 transition-[filter] duration-150 ease-out">
                {t("topbar.workspaces")}
              </Link>
            ) : (
              <>
                <Link to="/login" className="hidden sm:inline-flex h-9 px-2 items-center text-[13px] font-medium text-muted hover:text-ink transition-colors duration-150 ease-out">
                  {t("common.login")}
                </Link>
                <Link to="/login?mode=signup" className="h-9 px-4 rounded-[10px] bg-accent text-accent-ink text-[13px] font-medium inline-flex items-center whitespace-nowrap hover:brightness-110 transition-[filter] duration-150 ease-out">
                  {t("common.signup")}
                </Link>
              </>
            )
          }
        >
          <nav className="hidden md:flex items-center gap-1 ml-6 text-[14px]">
            <a href="#how" className="px-3 h-9 inline-flex items-center rounded-lg text-muted hover:text-ink transition-colors duration-150 ease-out">{t("landing.nav.how")}</a>
            <a href="#teams" className="px-3 h-9 inline-flex items-center rounded-lg text-muted hover:text-ink transition-colors duration-150 ease-out">{t("landing.nav.teams")}</a>
          </nav>
        </TopBar>

        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pt-28 sm:pt-40 lg:pt-44 pb-10">
          <motion.div
            data-theme="dark"
            className="max-w-[640px] bg-transparent"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            <h1 className="text-[40px] sm:text-[56px] leading-[1.04] font-medium text-ink tracking-[-0.03em] text-balance">{t("landing.title")}</h1>
            <p className="mt-5 text-[18px] leading-relaxed text-ink/80 max-w-xl text-pretty">{t("landing.subtitle")}</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <CtaLink to={appLink}>
                {t("landing.cta")}
                <ArrowRight size={16} strokeWidth={1.75} />
              </CtaLink>
              <CtaLink to="/login?demo=1" variant="glass">{t("landing.secondary")}</CtaLink>
            </div>
          </motion.div>
        </div>
        </div>

        {/* the brief rises out of the scene and runs past the fold */}
        <div className="relative max-w-6xl mx-auto px-4 sm:px-6 pt-4 sm:pt-14 lg:pt-20 pb-16 sm:pb-24">
          <div className="mx-auto max-w-5xl">
            <HeroDemo />
          </div>
        </div>
      </section>

      {/* ------------------------------------------------ how it works */}
      <section id="how" className="scroll-mt-8 border-t border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
          <SectionHead eyebrow={t("landing.how.eyebrow")} title={t("landing.how.title")} subtitle={t("landing.how.subtitle")} />
          <ol className="mt-12 grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <Step n={1} title={t("landing.how.s1.title")} body={t("landing.how.s1.body")}>
              <div className="flex flex-wrap gap-1.5">
                <Chip icon={<HnMark />}>Hacker News</Chip>
                <Chip icon={<span className="w-1.5 h-1.5 rounded-full bg-faint" />}>Google News</Chip>
                <Chip icon={<FileIcon size={14} className="text-muted" />}>{t("landing.how.yourFiles")}</Chip>
              </div>
            </Step>
            <Step n={2} title={t("landing.how.s2.title")} body={t("landing.how.s2.body")}>
              <figure className="rounded-xl border border-line bg-bg p-3">
                <blockquote className="text-[13px] leading-snug text-ink">{t("landing.how.sampleQuote")}</blockquote>
                <figcaption className="mt-2 flex flex-col gap-1 text-[12px]">
                  <span className="text-faint">{t("landing.how.sampleSource")}</span>
                  <span className="inline-flex items-center gap-1 text-rising font-medium whitespace-nowrap">
                    <Check size={12} strokeWidth={2} /> {t("landing.how.verified")}
                  </span>
                </figcaption>
              </figure>
            </Step>
            <Step n={3} title={t("landing.how.s3.title")} body={t("landing.how.s3.body")}>
              <WeighFragment />
            </Step>
            <Step n={4} title={t("landing.how.s4.title")} body={t("landing.how.s4.body")}>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 rounded-lg border border-line bg-bg px-3 h-9 text-[12px]">
                  <FileIcon size={14} className="text-muted" />
                  <span className="reading text-ink truncate">brief-2026-11-16.html</span>
                </div>
                <div className="flex items-center gap-2 rounded-lg border border-line bg-bg px-3 h-9 text-[12px]">
                  <FileIcon size={14} className="text-muted" />
                  <span className="text-ink truncate">{t("landing.how.trace")}</span>
                </div>
                <div className="text-[12px] text-faint mt-0.5">{t("landing.how.cost")}</div>
              </div>
            </Step>
          </ol>
        </div>
      </section>

      {/* ------------------------------------------------ teams */}
      <section id="teams" className="scroll-mt-20 border-t border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-16 sm:py-24">
          <SectionHead eyebrow={t("landing.teams.eyebrow")} title={t("landing.teams.title")} subtitle={t("landing.teams.subtitle")} />
          <div className="mt-12 grid lg:grid-cols-[minmax(0,1fr)_300px] gap-5 items-start">
            <div className="grid md:grid-cols-3 gap-4">
              {(["t1", "t2", "t3"] as const).map((k) => (
                <figure key={k} className="rounded-2xl border border-line bg-surface shadow-card p-6 flex flex-col">
                  <blockquote className="text-[15px] leading-relaxed text-ink text-pretty">“{t(`landing.teams.${k}.quote`)}”</blockquote>
                  <figcaption className="mt-auto pt-5 text-[13px] text-muted">{t(`landing.teams.${k}.team`)}</figcaption>
                </figure>
              ))}
            </div>
            <figure className="hidden lg:block rounded-2xl border border-line bg-surface p-2 shadow-card">
              <img
                src="/brand/photos/people.jpg"
                alt={t("landing.teams.photoAlt")}
                loading="lazy"
                width={1333}
                height={2000}
                className="w-full aspect-[4/5] object-cover rounded-[10px]"
              />
              <figcaption className="px-2 pt-3 pb-1 text-[12px] text-muted leading-snug">{t("landing.teams.photoCaption")}</figcaption>
            </figure>
          </div>

          <div className="mt-10 rounded-[20px] border border-line bg-surface shadow-card p-6 sm:p-10 flex flex-col md:flex-row md:items-center gap-6">
            <div className="flex-1">
              <h3 className="text-[28px] font-medium text-ink leading-tight tracking-[-0.02em]">{t("landing.teams.ctaTitle")}</h3>
              <p className="mt-2 text-[15px] leading-relaxed text-muted max-w-xl">{t("landing.teams.ctaBody")}</p>
            </div>
            <CtaLink to={me ? "/app" : "/login?mode=signup"}>
              {t("landing.teams.cta")}
              <ArrowRight size={16} strokeWidth={1.75} />
            </CtaLink>
          </div>
        </div>
      </section>

      <footer className="border-t border-line">
        <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 flex flex-col sm:flex-row gap-2 justify-between text-[13px] text-faint">
          <span>© 2026 Tellwind</span>
          <span>{t("landing.footer")}</span>
        </div>
      </footer>
    </div>
  );
}

function Step({ n, title, body, children }: { n: number; title: string; body: string; children: ReactNode }) {
  return (
    <li className="rounded-2xl border border-line bg-surface shadow-card p-5 flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <span className="reading w-7 h-7 rounded-lg bg-surface-2 text-muted text-[13px] flex items-center justify-center">{n}</span>
        <h3 className="font-medium text-ink text-[15px]">{title}</h3>
      </div>
      <div className="min-h-[92px]">{children}</div>
      <p className="text-[14px] leading-relaxed text-muted text-pretty">{body}</p>
    </li>
  );
}

function Chip({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-bg px-2.5 h-7 text-[12px] text-muted">
      {icon}
      {children}
    </span>
  );
}

/** Four weeks of daily volume with one busy day capped, and a held call. */
function WeighFragment() {
  const { t } = useTranslation();
  const bars = [3, 4, 2, 5, 4, 3, 6, 4, 5, 3, 4, 14, 5, 6, 5, 7, 6, 8, 7];
  const cap = 9;
  return (
    <div className="rounded-xl border border-line bg-bg p-3">
      <div className="flex items-end gap-[3px] h-12">
        {bars.map((b, i) => {
          const over = b > cap;
          return (
            <span key={i} className="relative flex-1 flex flex-col justify-end h-full">
              {over && <span className="absolute w-full rounded-sm border border-dashed border-fading/60" style={{ bottom: `${(cap / 14) * 100}%`, height: `${((b - cap) / 14) * 100}%` }} />}
              <span
                className="w-full rounded-sm"
                style={{
                  height: `${(Math.min(b, cap) / 14) * 100}%`,
                  background: i >= bars.length - 7 ? "var(--rising)" : "var(--line-strong)",
                  opacity: i >= bars.length - 7 ? 0.85 : 1,
                }}
              />
            </span>
          );
        })}
      </div>
      <div className="mt-2 flex items-center justify-between gap-2 text-[12px]">
        <span className="text-fading font-medium">{t("landing.how.capped")}</span>
        <span className="inline-flex items-center gap-1 font-medium" style={{ color: verdictVar("rising") }}>
          <VerdictIcon verdict="rising" size={12} /> {t("landing.how.held")}
        </span>
      </div>
    </div>
  );
}
