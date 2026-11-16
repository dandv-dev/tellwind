import { Check, ChevronDown, Globe, Moon, Sun } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { LANGS } from "../i18n";
import { useLogout, useMe } from "../lib/auth";
import { useTheme } from "../lib/theme";
import { Logo } from "./Logo";

/** One small globe menu everywhere: always in the bar, so the language is easy to find. */
export function LangSwitch(_: { compact?: boolean } = {}) {
  return <LangMenu />;
}

function LangMenu() {
  const { i18n, t } = useTranslation();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const cur = LANGS.find((l) => l.code === i18n.language) ?? LANGS[0];
  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        aria-label={t("common.language")}
        aria-expanded={open}
        className="h-8 pl-2.5 pr-2 rounded-full border border-line inline-flex items-center gap-1.5 text-[12px] font-medium text-ink hover:border-line-strong transition-colors duration-150 ease-out"
      >
        <Globe size={14} strokeWidth={1.5} className="text-muted" />
        {cur.short}
        <ChevronDown size={14} strokeWidth={1.5} className="text-muted" />
      </button>
      {open && (
        <div role="menu" className="absolute right-0 mt-2 w-44 rounded-xl border border-line bg-surface shadow-pop p-1.5 z-40">
          {LANGS.map((l) => (
            <button
              key={l.code}
              role="menuitemradio"
              aria-checked={i18n.language === l.code}
              onClick={() => {
                i18n.changeLanguage(l.code);
                setOpen(false);
              }}
              className="w-full flex items-center gap-2 px-3 h-9 rounded-lg text-[13px] text-ink hover:bg-surface-2 text-left"
            >
              <span className="flex-1">{l.label}</span>
              {i18n.language === l.code && <Check size={14} strokeWidth={1.75} className="text-muted" />}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ThemeSwitch() {
  const { theme, toggle } = useTheme();
  const { t } = useTranslation();
  const dark = theme === "dark";
  return (
    <button
      onClick={toggle}
      aria-label={`${t("common.theme")}: ${dark ? t("common.dark") : t("common.light")}`}
      title={dark ? t("common.light") : t("common.dark")}
      className="relative w-8 h-8 rounded-full border border-line flex items-center justify-center text-muted hover:text-ink transition-colors duration-150 ease-out overflow-hidden"
    >
      <Sun size={16} strokeWidth={1.5} className={`absolute transition-[opacity,transform] duration-300 ease-out ${dark ? "opacity-0 -rotate-90 scale-50" : "opacity-100"}`} />
      <Moon size={16} strokeWidth={1.5} className={`absolute transition-[opacity,transform] duration-300 ease-out ${dark ? "opacity-100" : "opacity-0 rotate-90 scale-50"}`} />
    </button>
  );
}

function AccountMenu() {
  const { data: me } = useMe();
  const { t } = useTranslation();
  const logout = useLogout();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  if (!me) return null;
  const initials = (me.name || me.email).split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className="relative" ref={ref}>
      <button onClick={() => setOpen(!open)} className="w-8 h-8 rounded-full border border-line bg-surface-2 text-ink text-[12px] font-medium hover:border-line-strong transition-colors duration-150 ease-out" aria-label={t("topbar.account")} aria-expanded={open}>
        {initials}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-64 rounded-xl border border-line bg-surface shadow-pop p-1.5 z-40">
          <div className="px-3 py-2">
            <div className="text-[13px] font-medium text-ink truncate">{me.name}</div>
            <div className="text-[12px] text-faint truncate">{me.email}</div>
          </div>
          <ThemeChoice />
          <Link to="/app" onClick={() => setOpen(false)} className="block px-3 py-2 rounded-lg text-[13px] text-ink hover:bg-surface-2">
            {t("topbar.workspaces")}
          </Link>
          <button
            onClick={() => logout.mutate(undefined, { onSuccess: () => nav("/") })}
            className="w-full text-left px-3 py-2 rounded-lg text-[13px] text-ink hover:bg-surface-2"
          >
            {t("common.logout")}
          </button>
        </div>
      )}
    </div>
  );
}

/** Light / dark as a two-way switch inside the account menu. */
function ThemeChoice() {
  const { theme, toggle } = useTheme();
  const { t } = useTranslation();
  const opts = [
    { key: "light", label: t("common.light"), Icon: Sun },
    { key: "dark", label: t("common.dark"), Icon: Moon },
  ] as const;
  return (
    <div className="px-3 py-2 border-y border-line my-1 flex items-center justify-between gap-3">
      <span className="text-[13px] text-muted">{t("common.theme")}</span>
      <div role="radiogroup" aria-label={t("common.theme")} className="grid grid-cols-2 p-0.5 rounded-lg bg-surface-2">
        {opts.map(({ key, label, Icon }) => (
          <button
            key={key}
            role="radio"
            aria-checked={theme === key}
            onClick={() => theme !== key && toggle()}
            className={`h-7 px-2 rounded-md inline-flex items-center gap-1.5 text-[12px] font-medium transition-colors duration-150 ease-out ${
              theme === key ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"
            }`}
          >
            <Icon size={14} strokeWidth={1.5} />
            {label}
          </button>
        ))}
      </div>
    </div>
  );
}

/**
 * `overlay`: the bar sits on the landing scene (a dark photo) instead of the page,
 * so it is transparent and uses the dark tokens whatever the theme.
 */
export function TopBar({ children, logoTo = "/", right, overlay = false }: { children?: ReactNode; logoTo?: string; right?: ReactNode; overlay?: boolean }) {
  const { data: me } = useMe();
  return (
    <header
      data-theme={overlay ? "dark" : undefined}
      className={overlay ? "absolute inset-x-0 top-0 z-30" : "sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur-md"}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 h-16 flex items-center gap-3">
        <Link to={logoTo} className="shrink-0 flex items-center" aria-label="Tellwind">
          <span className="hidden min-[400px]:flex"><Logo height={28} on={overlay ? "dark" : undefined} /></span>
          <span className="flex min-[400px]:hidden"><Logo variant="icon" height={28} on={overlay ? "dark" : undefined} /></span>
        </Link>
        <div className="flex-1 min-w-0 flex items-center self-stretch">{children}</div>
        <div className="flex items-center gap-2">
          <LangSwitch />
          {/* Signed in, the theme lives in the account menu; signed out it keeps its own button. */}
          {me ? <AccountMenu /> : <ThemeSwitch />}
          {right}
        </div>
      </div>
    </header>
  );
}
