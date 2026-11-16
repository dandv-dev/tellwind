import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { Logo } from "../components/Logo";
import { LangSwitch, ThemeSwitch } from "../components/TopBar";
import { Button, Field, Input } from "../components/ui";
import { api, ApiError } from "../lib/api";
import { useMe } from "../lib/auth";
import type { User } from "../lib/types";

const DEMO = [
  { role: "owner", email: "owner@demo.tellwind.app", name: "Maya Okafor" },
  { role: "member", email: "member@demo.tellwind.app", name: "Jonas Lindqvist" },
  { role: "viewer", email: "viewer@demo.tellwind.app", name: "Priya Raman" },
];
const DEMO_PASSWORD = "tellwind-demo";

export default function Auth() {
  const { t } = useTranslation();
  const [params, setParams] = useSearchParams();
  const mode = params.get("mode") === "signup" ? "signup" : "login";
  const next = params.get("next") || "/app";
  const nav = useNavigate();
  const qc = useQueryClient();
  const { data: me, isLoading } = useMe();
  const [email, setEmail] = useState(params.get("email") ?? "");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!isLoading && me) return <Navigate to={next} replace />;

  const submit = async (e: FormEvent, override?: { email: string; password: string }) => {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      const body = override ?? (mode === "signup" ? { email, password, name } : { email, password });
      const user = await api<User>(`/auth/${override ? "login" : mode}`, { body });
      qc.setQueryData(["me"], user);
      nav(next, { replace: true });
    } catch (ex) {
      const code = ex instanceof ApiError ? ex.code : "generic";
      setErr(t(`auth.errors.${code}`, { defaultValue: t("auth.errors.generic") }));
    } finally {
      setBusy(false);
    }
  };

  const setMode = (m: "login" | "signup") => {
    const p = new URLSearchParams(params);
    if (m === "signup") p.set("mode", "signup");
    else p.delete("mode");
    setParams(p, { replace: true });
    setErr(null);
  };

  return (
    <div className="min-h-dvh grid lg:grid-cols-[1.05fr_1fr]">
      <aside className="relative hidden lg:flex flex-col justify-between p-10 overflow-hidden text-[#F5F1EA]">
        <img src="/brand/photos/visual-element.jpg" alt="" className="absolute inset-0 w-full h-full object-cover" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#12202E]/70 via-[#12202E]/30 to-[#12202E]/85" />
        <Link to="/" className="relative">
          <img src="/brand/logo/svg/tellwind-horizontal-on-dark.svg" alt="Tellwind" className="h-8" />
        </Link>
        <div className="relative max-w-md">
          <p className="text-[32px] font-medium leading-tight tracking-[-0.02em]">{t("auth.tagline")}</p>
          <p className="mt-3 text-[#F5F1EA]/75 text-[15px]">{t("landing.subtitle")}</p>
        </div>
      </aside>

      <main className="flex flex-col">
        <div className="flex items-center justify-between p-4 sm:p-6">
          <Link to="/" className="lg:invisible">
            <Logo height={26} />
          </Link>
          <div className="flex items-center gap-2">
            <LangSwitch compact />
            <ThemeSwitch />
          </div>
        </div>
        <div className="flex-1 flex items-center justify-center px-4 pb-10">
          <div className="w-full max-w-[400px]">
            <div className="grid grid-cols-2 p-1 rounded-[10px] bg-surface-2 mb-8" role="tablist">
              {(["login", "signup"] as const).map((m) => (
                <button
                  key={m}
                  role="tab"
                  aria-selected={mode === m}
                  onClick={() => setMode(m)}
                  className={`h-9 rounded-md text-[14px] font-medium transition-colors duration-150 ease-out ${mode === m ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"}`}
                >
                  {t(m === "login" ? "auth.loginTab" : "auth.signupTab")}
                </button>
              ))}
            </div>
            <h1 className="text-[28px] font-medium text-ink tracking-[-0.02em] mb-6">{t(mode === "login" ? "auth.welcome" : "auth.create")}</h1>
            <form onSubmit={submit} className="flex flex-col gap-4">
              {mode === "signup" && (
                <Field label={t("common.name")}>
                  <Input value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" />
                </Field>
              )}
              <Field label={t("common.email")}>
                <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" />
              </Field>
              <Field label={t("common.password")} hint={mode === "signup" ? t("auth.passwordHint") : undefined}>
                <Input
                  type="password"
                  required
                  minLength={mode === "signup" ? 8 : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                />
              </Field>
              {err && <p className="text-[13px] text-fading bg-fading-soft rounded-lg px-3 py-2">{err}</p>}
              <Button type="submit" size="lg" loading={busy}>
                {t(mode === "login" ? "common.login" : "common.signup")}
              </Button>
            </form>

            <div className="mt-8 rounded-2xl border border-line bg-surface p-5">
              <div className="text-[13px] font-medium text-ink">{t("auth.demoTitle")}</div>
              <p className="text-[12px] text-muted mt-1 mb-4">{t("auth.demoHint", { password: DEMO_PASSWORD })}</p>
              <div className="grid grid-cols-3 gap-2">
                {DEMO.map((d) => (
                  <button
                    key={d.role}
                    disabled={busy}
                    onClick={(e) => submit(e, { email: d.email, password: DEMO_PASSWORD })}
                    className="rounded-[10px] border border-line px-3 py-2 text-left hover:border-line-strong hover:bg-surface-2 transition-colors duration-150 ease-out disabled:opacity-50"
                    title={d.email}
                  >
                    <div className="text-[13px] font-medium text-ink">{t(`common.roles.${d.role}`)}</div>
                    <div className="text-[12px] text-faint truncate">{d.name}</div>
                  </button>
                ))}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
