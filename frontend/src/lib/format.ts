import i18n from "../i18n";

const locale = () => (i18n.language === "uk" ? "uk-UA" : i18n.language === "ru" ? "ru-RU" : "en-GB");

export function fmtDate(
  iso: string | null | undefined,
  opts: Intl.DateTimeFormatOptions = { day: "numeric", month: "short" },
) {
  if (!iso) return "";
  const d = iso.length === 10 ? new Date(iso + "T12:00:00Z") : new Date(iso);
  return new Intl.DateTimeFormat(locale(), { timeZone: "UTC", ...opts }).format(d);
}

export const fmtDay = (iso: string | null | undefined) =>
  fmtDate(iso, { weekday: "short", day: "numeric", month: "short" });

export const fmtLongDay = (iso: string | null | undefined) =>
  fmtDate(iso, { weekday: "long", day: "numeric", month: "long", year: "numeric" });

export const fmtDateTime = (iso: string | null | undefined) =>
  fmtDate(iso, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

export function fmtCost(usd: number | undefined | null) {
  if (usd == null) return "";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(usd < 1 ? 3 : 2)}`;
}

export function fmtPct(p: number | null | undefined) {
  if (p == null) return "—";
  const v = Math.max(-999, Math.min(999, Math.round(p)));
  return `${v > 0 ? "+" : v < 0 ? "−" : "±"}${Math.abs(v)}%`;
}

export function fmtBytes(n: number) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function fmtDuration(a: string | null, b: string | null) {
  if (!a || !b) return "";
  const s = Math.max(0, Math.round((new Date(b).getTime() - new Date(a).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

export function domainOf(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}
