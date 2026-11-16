import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { ChevronRight, Plus, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate } from "react-router-dom";
import { VerdictIcon } from "../brief/bits";
import { TopBar } from "../components/TopBar";
import { Button, Card, Empty, Field, Input, RoleBadge, Spinner, Textarea } from "../components/ui";
import { api } from "../lib/api";
import { fmtDay } from "../lib/format";
import type { Invitation, Verdict, Workspace } from "../lib/types";

export default function Workspaces() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [creating, setCreating] = useState(false);
  const q = useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api<{ workspaces: Workspace[]; invitations: Invitation[] }>("/workspaces"),
  });
  const respond = useMutation({
    mutationFn: ({ id, action }: { id: string; action: "accept" | "decline" }) =>
      api<{ workspace_id?: string }>(`/invitations/${id}/${action}`, { method: "POST" }),
    onSuccess: (r, v) => {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      if (v.action === "accept" && r.workspace_id) nav(`/app/w/${r.workspace_id}`);
    },
  });

  return (
    <div className="min-h-dvh">
      <TopBar logoTo="/app" />
      <main className="max-w-6xl mx-auto px-4 sm:px-6 pt-6 pb-16 sm:pt-8">
        <div className="flex items-end justify-between gap-4 mb-8 sm:mb-10 flex-wrap">
          <h1 className="text-[28px] sm:text-[32px] font-medium text-ink tracking-[-0.02em]">{t("workspaces.title")}</h1>
          <Button onClick={() => setCreating(true)}>
            <Plus size={16} strokeWidth={1.75} />
            {t("workspaces.newWorkspace")}
          </Button>
        </div>

        {q.data && q.data.invitations.length > 0 && (
          <section className="mb-8 sm:mb-10">
            <h2 className="text-[18px] font-medium text-ink mb-4">{t("workspaces.invitations")}</h2>
            <Card className="divide-y divide-line">
              {q.data.invitations.map((inv) => (
                <div key={inv.id} className="px-4 sm:px-5 py-4 flex flex-col sm:flex-row sm:items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="text-[15px] font-medium text-ink truncate">{inv.workspace?.name}</div>
                    <div className="text-[13px] text-muted truncate">
                      {inv.workspace?.subject} · {t("workspaces.invitedAs", { role: t(`common.roles.${inv.role}`).toLowerCase() })}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <Button size="sm" variant="ghost" onClick={() => respond.mutate({ id: inv.id, action: "decline" })}>
                      {t("common.decline")}
                    </Button>
                    <Button size="sm" onClick={() => respond.mutate({ id: inv.id, action: "accept" })}>
                      {t("common.accept")}
                    </Button>
                  </div>
                </div>
              ))}
            </Card>
          </section>
        )}

        {q.isLoading ? (
          <div className="py-20 flex justify-center text-muted"><Spinner /></div>
        ) : q.data && q.data.workspaces.length === 0 ? (
          <Empty title={t("workspaces.newWorkspace")}>
            <p>{t("workspaces.empty")}</p>
            <Button className="mt-4" onClick={() => setCreating(true)}>{t("workspaces.newWorkspace")}</Button>
          </Empty>
        ) : (
          <Card className="overflow-hidden">
            <div className="hidden sm:grid grid-cols-[minmax(0,1fr)_240px_96px_88px_16px] gap-x-4 px-5 h-10 items-center border-b border-line text-[12px] text-muted">
              <span>{t("workspaces.cols.workspace")}</span>
              <span>{t("workspaces.cols.brief")}</span>
              <span>{t("workspaces.cols.people")}</span>
              <span>{t("common.role")}</span>
              <span />
            </div>
            <div className="divide-y divide-line">
              {q.data?.workspaces.map((w) => <WorkspaceRow key={w.id} w={w} />)}
            </div>
          </Card>
        )}
      </main>
      {creating && <CreateDialog onClose={() => setCreating(false)} />}
    </div>
  );
}

function WorkspaceRow({ w }: { w: Workspace }) {
  const { t } = useTranslation();
  const tally = w.latest_brief?.tally ?? {};
  const total = Object.values(tally).reduce((a, b) => a + (b ?? 0), 0);
  return (
    <Link
      to={`/app/w/${w.id}`}
      className="group grid grid-cols-[minmax(0,1fr)_auto] sm:grid-cols-[minmax(0,1fr)_240px_96px_88px_16px] gap-x-4 gap-y-2 px-4 sm:px-5 py-4 items-center hover:bg-surface-2 transition-colors duration-150 ease-out"
    >
      <div className="min-w-0">
        <div className="flex items-baseline gap-2 min-w-0">
          <span className="text-[15px] font-medium text-ink truncate">{w.name}</span>
          {w.is_demo && <span className="shrink-0 text-[12px] text-faint">{t("common.demo")}</span>}
        </div>
        <div className="mt-0.5 text-[13px] text-muted truncate">{w.subject}</div>
      </div>
      <div className="col-start-2 row-start-1 sm:col-start-4 justify-self-end sm:justify-self-start">
        <RoleBadge role={w.role} label={t(`common.roles.${w.role}`)} />
      </div>
      <div className="col-span-2 sm:col-span-1 sm:col-start-2 sm:row-start-1 flex items-center gap-x-4 gap-y-1 flex-wrap text-[12px] text-muted">
        {total > 0 ? (
          <span className="inline-flex items-center gap-3">
            {(["rising", "steady", "fading"] as Verdict[]).map((v) => (
              <span key={v} className="inline-flex items-center gap-1" title={t(`verdict.${v}`)}>
                <VerdictIcon verdict={v} size={14} />
                <span className="reading text-ink">{tally[v] ?? 0}</span>
              </span>
            ))}
          </span>
        ) : null}
        <span className="reading text-faint">{w.latest_brief ? fmtDay(w.latest_brief.date) : t("workspaces.noBriefYet")}</span>
        <span className="sm:hidden text-faint">{t("workspaces.members", { count: w.members ?? 1 })}</span>
      </div>
      <span className="hidden sm:block sm:col-start-3 sm:row-start-1 reading text-[13px] text-muted">{w.members ?? 1}</span>
      <ChevronRight size={16} strokeWidth={1.5} className="hidden sm:block text-faint group-hover:text-ink transition-colors duration-150 ease-out" />
    </Link>
  );
}

const SUGGESTED: Record<string, string[]> = {
  "electric cars": ["Solid-state batteries", "Charging networks", "EV prices", "Chinese EV exports", "Autonomous driving", "Battery recycling"],
  "ai developer tools": ["Coding agents", "AI code review", "Model Context Protocol", "AI testing", "Local coding models"],
  "specialty coffee": ["Coffee prices", "Climate and harvests", "Cold brew", "Specialty cafés", "Direct trade"],
};

function CreateDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const nav = useNavigate();
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [subject, setSubject] = useState("");
  const [desc, setDesc] = useState("");
  const [topics, setTopics] = useState<string[]>(["", "", ""]);
  const create = useMutation({
    mutationFn: () =>
      api<Workspace>("/workspaces", {
        body: {
          name: name.trim() || subject.trim(),
          subject: subject.trim(),
          subject_description: desc.trim(),
          topics: topics.map((x) => x.trim()).filter(Boolean).map((n) => ({ name: n })),
        },
      }),
    onSuccess: (w) => {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      nav(`/app/w/${w.id}`);
    },
  });
  const sugg = SUGGESTED[subject.trim().toLowerCase()] ?? [];
  const submit = (e: FormEvent) => {
    e.preventDefault();
    create.mutate();
  };
  const filled = topics.filter((x) => x.trim()).length;

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div className="absolute inset-0 bg-[#0b1520]/45 backdrop-blur-[2px]" onClick={onClose} />
      <form onSubmit={submit} className="relative w-full sm:max-w-lg max-h-[92dvh] overflow-y-auto rounded-t-[20px] sm:rounded-[20px] bg-bg border border-line shadow-pop p-6 flex flex-col gap-4">
        <div>
          <h2 className="text-[20px] font-medium text-ink">{t("workspaces.createTitle")}</h2>
          <p className="text-[13px] text-muted mt-1">{t("workspaces.createHint")}</p>
        </div>
        <Field label={t("team.subject")}>
          <Input required minLength={2} value={subject} onChange={(e) => setSubject(e.target.value)} placeholder={t("workspaces.subjectPlaceholder")} autoFocus />
        </Field>
        <Field label={t("team.wsName")}>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={t("workspaces.namePlaceholder")} />
        </Field>
        <Field label={t("team.subjectDesc")}>
          <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} rows={2} />
        </Field>
        <div className="flex flex-col gap-2">
          <div className="flex items-baseline justify-between">
            <span className="text-[13px] font-medium text-ink">{t("team.watchlist")}</span>
            <span className="reading text-[12px] text-faint">{filled}/10</span>
          </div>
          {topics.map((tp, i) => (
            <div key={i} className="flex gap-2">
              <Input value={tp} onChange={(e) => setTopics(topics.map((x, j) => (j === i ? e.target.value : x)))} placeholder={t("workspaces.topicPlaceholder")} className="h-10" />
              {topics.length > 1 && (
                <Button type="button" variant="ghost" size="sm" className="h-10" onClick={() => setTopics(topics.filter((_, j) => j !== i))} aria-label={t("team.removeTopic")}>
                  <X size={16} strokeWidth={1.5} />
                </Button>
              )}
            </div>
          ))}
          {topics.length < 10 && (
            <Button type="button" variant="ghost" size="sm" className="self-start" onClick={() => setTopics([...topics, ""])}>
              <Plus size={16} strokeWidth={1.5} /> {t("team.addTopic")}
            </Button>
          )}
          {sugg.length > 0 && (
            <div className="flex flex-wrap gap-1.5 items-center">
              <span className="text-[12px] text-faint mr-1">{t("workspaces.suggest")}:</span>
              {sugg.filter((s) => !topics.includes(s)).map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() => {
                    const empty = topics.findIndex((x) => !x.trim());
                    if (empty >= 0) setTopics(topics.map((x, j) => (j === empty ? s : x)));
                    else if (topics.length < 10) setTopics([...topics, s]);
                  }}
                  className="inline-flex items-center gap-1 rounded-lg border border-line px-2 h-7 text-[12px] text-muted hover:border-line-strong hover:text-ink transition-colors duration-150 ease-out"
                >
                  <Plus size={12} strokeWidth={1.5} /> {s}
                </button>
              ))}
            </div>
          )}
        </div>
        {create.isError && <p className="text-[13px] text-fading">{t("common.error")}</p>}
        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={onClose}>{t("common.cancel")}</Button>
          <Button type="submit" loading={create.isPending} disabled={!subject.trim() || filled === 0}>
            {t("common.create")}
          </Button>
        </div>
      </form>
    </div>
  );
}
