import { ChevronDown, Mail, Plus, Trash2, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Button, Card, Field, Input, RoleBadge, Select, Textarea } from "../../components/ui";
import { api, ApiError } from "../../lib/api";
import { useMe } from "../../lib/auth";
import { fmtDate } from "../../lib/format";
import type { Invitation, Role, Topic, User } from "../../lib/types";
import { useWorkspace } from "./Layout";

interface Member {
  id: string;
  role: Role;
  user: User;
  joined_at: string;
}

const ROLES: Role[] = ["owner", "member", "viewer"];

/** Avatar, person, role, action. Shared by the header, member and invitation rows. */
const PEOPLE_ROW = "grid grid-cols-[36px_minmax(0,1fr)_32px] sm:grid-cols-[36px_minmax(0,1fr)_128px_32px] gap-x-3 px-4";

export default function TeamTab() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const owner = ws.role === "owner";
  const q = useQuery({
    queryKey: ["members", ws.id],
    queryFn: () => api<{ members: Member[]; invitations: Invitation[] }>(`/workspaces/${ws.id}/members`),
  });
  const invitations = owner ? (q.data?.invitations ?? []) : [];
  return (
    <div className="flex flex-col gap-8 sm:gap-10">
      <div>
        <h1 className="text-[28px] sm:text-[32px] font-medium text-ink tracking-[-0.02em]">{t("team.tab")}</h1>
        {!owner && <p className="text-[13px] text-muted mt-1">{t("team.ownerOnly")}</p>}
      </div>

      <section className="flex flex-col gap-4">
        <h2 className="text-[18px] font-medium text-ink">{t("team.people")}</h2>
        <div className="grid lg:grid-cols-[minmax(0,1fr)_340px] gap-6 items-start">
          <Card className="overflow-hidden">
            <div className={`hidden sm:grid ${PEOPLE_ROW} h-10 items-center border-b border-line text-[12px] text-muted`}>
              <span className="col-span-2">{t("team.person")}</span>
              <span>{t("common.role")}</span>
              <span />
            </div>
            <div className="divide-y divide-line">
              {q.data?.members.map((m) => <MemberRow key={m.id} m={m} editable={owner} />)}
            </div>
            {invitations.length > 0 && (
              <>
                <div className="px-4 h-10 flex items-center gap-2 border-y border-line bg-surface-2/40 text-[12px] text-muted">
                  {t("team.invitations")}
                  <span className="reading text-faint">{invitations.length}</span>
                </div>
                <div className="divide-y divide-line">
                  {invitations.map((i) => <InviteRow key={i.id} inv={i} />)}
                </div>
              </>
            )}
          </Card>
          {owner ? <InviteForm /> : <RolesHelp />}
        </div>
      </section>

      <Settings editable={owner} />
    </div>
  );
}

function RolesHelp() {
  const { t } = useTranslation();
  return (
    <Card className="p-5 flex flex-col gap-4">
      {ROLES.map((r) => (
        <div key={r}>
          <RoleBadge role={r} label={t(`common.roles.${r}`)} />
          <p className="text-[13px] text-muted mt-1">{t(`common.roleHints.${r}`)}</p>
        </div>
      ))}
    </Card>
  );
}

const iconBtn =
  "w-8 h-8 rounded-[10px] flex items-center justify-center text-faint hover:text-fading hover:bg-fading-soft transition-colors duration-150 ease-out";

function MemberRow({ m, editable }: { m: Member; editable: boolean }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const { data: me } = useMe();
  const qc = useQueryClient();
  const [err, setErr] = useState<string | null>(null);
  const onErr = (e: Error) => setErr(e instanceof ApiError && e.code === "last_owner" ? t("team.lastOwner") : t("common.error"));
  const role = useMutation({
    mutationFn: (r: Role) => api(`/workspaces/${ws.id}/members/${m.id}`, { method: "PATCH", body: { role: r } }),
    onSuccess: () => {
      setErr(null);
      qc.invalidateQueries({ queryKey: ["members", ws.id] });
    },
    onError: onErr,
  });
  const remove = useMutation({
    mutationFn: () => api(`/workspaces/${ws.id}/members/${m.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", ws.id] }),
    onError: onErr,
  });
  const isMe = me?.id === m.user.id;
  const initials = (m.user.name || m.user.email).split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <div className={`${PEOPLE_ROW} py-3 gap-y-2 sm:items-center`}>
      <span className="row-span-2 sm:row-span-1 w-9 h-9 rounded-full bg-surface-2 text-[12px] font-medium text-muted flex items-center justify-center">{initials}</span>
      <div className="min-w-0 self-center">
        <div className="text-[14px] font-medium text-ink break-words sm:truncate">
          {m.user.name} {isMe && <span className="text-faint font-normal">({t("common.you")})</span>}
        </div>
        <div className="mt-0.5 text-[12px] text-faint break-words sm:truncate">
          {m.user.email} <span className="whitespace-nowrap">· {t("team.joined", { date: fmtDate(m.joined_at) })}</span>
        </div>
      </div>
      <div className="col-start-2 row-start-2 sm:col-start-3 sm:row-start-1">
        {editable ? (
          <Select value={m.role} onChange={(e) => role.mutate(e.target.value as Role)} className="!w-32 !h-9 text-[13px]" aria-label={t("common.role")} disabled={role.isPending}>
            {ROLES.map((r) => (
              <option key={r} value={r}>{t(`common.roles.${r}`)}</option>
            ))}
          </Select>
        ) : (
          <RoleBadge role={m.role} label={t(`common.roles.${m.role}`)} />
        )}
      </div>
      <div className="col-start-3 row-start-1 sm:col-start-4 self-center">
        {editable && !isMe && (
          <button onClick={() => remove.mutate()} className={iconBtn} aria-label={t("team.remove")} title={t("team.remove")}>
            <X size={16} strokeWidth={1.5} />
          </button>
        )}
      </div>
      {err && <p className="col-start-2 col-span-2 sm:col-span-3 text-[12px] text-fading">{err}</p>}
    </div>
  );
}

function InviteRow({ inv }: { inv: Invitation }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const revoke = useMutation({
    mutationFn: () => api(`/workspaces/${ws.id}/invitations/${inv.id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["members", ws.id] }),
  });
  return (
    <div className={`${PEOPLE_ROW} py-3 gap-y-2 sm:items-center`}>
      <span className="row-span-2 sm:row-span-1 w-9 h-9 rounded-full border border-dashed border-line-strong text-faint flex items-center justify-center">
        <Mail size={16} strokeWidth={1.5} />
      </span>
      <div className="min-w-0 self-center">
        <div className="text-[14px] text-ink break-words sm:truncate">{inv.email}</div>
        <div className="mt-0.5 text-[12px] text-faint">{t("team.sent", { date: fmtDate(inv.created_at) })}</div>
      </div>
      <div className="col-start-2 row-start-2 sm:col-start-3 sm:row-start-1">
        <RoleBadge role={inv.role} label={t(`common.roles.${inv.role}`)} />
      </div>
      <div className="col-start-3 row-start-1 sm:col-start-4 self-center">
        <button onClick={() => revoke.mutate()} disabled={revoke.isPending} className={iconBtn} aria-label={t("team.revoke")} title={t("team.revoke")}>
          <X size={16} strokeWidth={1.5} />
        </button>
      </div>
    </div>
  );
}

function InviteForm() {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [done, setDone] = useState<string | null>(null);
  const inv = useMutation({
    mutationFn: () => api(`/workspaces/${ws.id}/invitations`, { body: { email, role } }),
    onSuccess: () => {
      setDone(email);
      setEmail("");
      qc.invalidateQueries({ queryKey: ["members", ws.id] });
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setDone(null);
    inv.mutate();
  };
  return (
    <Card className="p-5">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <h3 className="text-[15px] font-medium text-ink">{t("team.inviteTitle")}</h3>
        <Field label={t("common.email")}>
          <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="name@company.com" />
        </Field>
        <div className="flex flex-col gap-1.5">
          <span className="text-[13px] font-medium text-ink">{t("common.role")}</span>
          <div role="radiogroup" aria-label={t("common.role")} className="grid grid-cols-3 p-1 rounded-[10px] bg-surface-2">
            {(["viewer", "member", "owner"] as Role[]).map((r) => (
              <button
                type="button"
                role="radio"
                aria-checked={role === r}
                key={r}
                onClick={() => setRole(r)}
                className={`h-8 rounded-md text-[13px] font-medium transition-colors duration-150 ease-out ${role === r ? "bg-surface text-ink shadow-card" : "text-muted hover:text-ink"}`}
              >
                {t(`common.roles.${r}`)}
              </button>
            ))}
          </div>
          <p className="text-[12px] text-muted">{t(`common.roleHints.${role}`)}</p>
        </div>
        <Button type="submit" loading={inv.isPending}>{t("common.invite")}</Button>
        {done && <p className="text-[13px] text-rising">{t("team.invited", { email: done })}</p>}
        {inv.error && <p className="text-[13px] text-fading">{(inv.error as ApiError).code === "already_member" ? t("team.alreadyMember") : t("common.error")}</p>}
        <p className="text-[12px] text-faint leading-relaxed">{t("team.inviteHint")}</p>
      </form>
    </Card>
  );
}

type Draft = Partial<Topic> & { kw: string; key: string; open?: boolean };

let draftSeq = 0;
const toDrafts = (topics: Topic[] | undefined): Draft[] =>
  (topics ?? []).map((tp) => ({ ...tp, kw: tp.keywords.join(", "), key: tp.id ?? `t${draftSeq++}` }));
const splitKw = (kw: string) => kw.split(",").map((k) => k.trim()).filter(Boolean);
const snapshot = (name: string, subject: string, desc: string, topics: Draft[]) =>
  JSON.stringify([name.trim(), subject.trim(), desc.trim(), topics.map((x) => [x.id ?? null, (x.name ?? "").trim(), (x.description ?? "").trim(), splitKw(x.kw)])]);

function Settings({ editable }: { editable: boolean }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [name, setName] = useState(ws.name);
  const [subject, setSubject] = useState(ws.subject);
  const [desc, setDesc] = useState(ws.subject_description);
  const [topics, setTopics] = useState<Draft[]>(() => toDrafts(ws.topics));
  const reset = () => {
    setName(ws.name);
    setSubject(ws.subject);
    setDesc(ws.subject_description);
    setTopics(toDrafts(ws.topics));
  };
  // Pick up the saved values once the workspace is refetched.
  useEffect(reset, [ws.name, ws.subject, ws.subject_description, ws.topics]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = snapshot(name, subject, desc, topics) !== snapshot(ws.name, ws.subject, ws.subject_description, toDrafts(ws.topics));
  const save = useMutation({
    mutationFn: async () => {
      await api(`/workspaces/${ws.id}`, { method: "PATCH", body: { name, subject, subject_description: desc } });
      await api(`/workspaces/${ws.id}/topics`, {
        method: "PUT",
        body: {
          topics: topics
            .filter((tp) => tp.name?.trim())
            .map((tp) => ({ id: tp.id, name: tp.name!.trim(), description: tp.description ?? "", keywords: splitKw(tp.kw) })),
        },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["workspace", ws.id] });
      qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
  const upd = (key: string, patch: Partial<Draft>) => setTopics(topics.map((x) => (x.key === key ? { ...x, ...patch } : x)));

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-baseline gap-3">
        <h2 className="text-[18px] font-medium text-ink">{t("team.settings")}</h2>
        {save.isSuccess && !dirty && <span className="text-[13px] text-rising">{t("common.saved")}</span>}
      </div>
      <div className="flex flex-col gap-6 min-w-0">
        <fieldset disabled={!editable} className="min-w-0">
        <Card className="p-5 sm:p-6 grid sm:grid-cols-2 gap-4">
          <Field label={t("team.wsName")}><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
          <Field label={t("team.subject")}><Input value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
          <div className="sm:col-span-2">
            <Field label={t("team.subjectDesc")}><Textarea rows={2} value={desc} onChange={(e) => setDesc(e.target.value)} /></Field>
          </div>
        </Card>
        </fieldset>

        <div className="flex flex-col gap-3">
          <div className="flex items-baseline justify-between gap-4">
            <div>
              <h3 className="text-[15px] font-medium text-ink">
                {t("team.watchlist")} <span className="reading text-[12px] text-faint font-normal ml-1">{topics.length}/10</span>
              </h3>
              <p className="text-[13px] text-muted mt-1">{t("team.watchlistHint")}</p>
            </div>
            {editable && topics.length < 10 && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={() => setTopics([...topics, { name: "", description: "", kw: "", key: `n${draftSeq++}`, open: true }])}
              >
                <Plus size={16} strokeWidth={1.5} />
                {t("team.addTopic")}
              </Button>
            )}
          </div>
          <Card className="overflow-hidden">
            <div className={`hidden sm:grid ${TOPIC_ROW} h-10 items-center border-b border-line text-[12px] text-muted`}>
              <span className="text-right">#</span>
              <span>{t("team.topicCols.topic")}</span>
              <span>{t("team.topicCols.covers")}</span>
              <span>{t("team.topicCols.phrases")}</span>
              <span />
            </div>
            <ol className="divide-y divide-line">
              {topics.map((tp, i) => (
                <TopicRow
                  key={tp.key}
                  n={i + 1}
                  tp={tp}
                  editable={editable}
                  onChange={(patch) => upd(tp.key, patch)}
                  onRemove={() => setTopics(topics.filter((x) => x.key !== tp.key))}
                />
              ))}
            </ol>
          </Card>
        </div>
      </div>

      <AnimatePresence>
        {editable && dirty && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="sticky bottom-4 z-10 mt-2 rounded-2xl border border-line-strong bg-surface shadow-pop px-4 py-3 flex items-center gap-3"
          >
            <span className="text-[13px] text-muted mr-auto">{save.isError ? <span className="text-fading">{t("common.error")}</span> : t("team.unsaved")}</span>
            <Button type="button" variant="ghost" onClick={reset} disabled={save.isPending}>{t("common.cancel")}</Button>
            <Button type="button" onClick={() => save.mutate()} loading={save.isPending}>{t("common.save")}</Button>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

/** Number, topic, what it covers, search phrases, actions. */
const TOPIC_ROW = "grid-cols-[20px_minmax(0,0.9fr)_minmax(0,1.4fr)_minmax(0,1.1fr)_32px] gap-x-4 px-4";

const rowBtn =
  "w-8 h-8 rounded-[10px] inline-flex items-center justify-center transition-colors duration-150 ease-out";

/**
 * A watchlist line. Collapsed it reads like a table row; opened, the same row
 * turns into its editor: each field sits in its own column, nothing repeats.
 */
function TopicRow({ n, tp, editable, onChange, onRemove }: { n: number; tp: Draft; editable: boolean; onChange: (p: Partial<Draft>) => void; onRemove: () => void }) {
  const { t } = useTranslation();
  const open = !!tp.open;
  const kws = splitKw(tp.kw);

  if (!open) {
    return (
      <li>
        <button
          type="button"
          onClick={() => onChange({ open: true })}
          aria-expanded={false}
          className="w-full text-left py-3 grid grid-cols-[20px_minmax(0,1fr)_32px] gap-x-3 sm:grid-cols-[20px_minmax(0,0.9fr)_minmax(0,1.4fr)_minmax(0,1.1fr)_32px] sm:gap-x-4 px-4 items-start hover:bg-surface-2 transition-colors duration-150 ease-out"
        >
          <span className="reading text-[12px] text-faint text-right leading-5">{n}</span>
          <span className="min-w-0">
            <span className={`block text-[14px] font-medium leading-5 ${tp.name ? "text-ink" : "text-faint"}`}>{tp.name || t("team.topicName")}</span>
            <span className="sm:hidden block text-[13px] text-muted mt-0.5 line-clamp-2">{tp.description}</span>
          </span>
          <span className="hidden sm:block text-[13px] text-muted leading-5 line-clamp-2">{tp.description || "—"}</span>
          <span className="hidden sm:block text-[12px] text-faint leading-5 truncate">{kws.length ? kws.join(", ") : t("team.phrasesAuto")}</span>
          <ChevronDown size={16} strokeWidth={1.5} className="col-start-3 row-start-1 sm:col-start-5 justify-self-center mt-0.5 text-faint" />
        </button>
      </li>
    );
  }

  const label = "text-[12px] text-muted sm:sr-only";
  const area = "!min-h-0 resize-none text-[13px] leading-5";
  return (
    <li className="bg-surface-2/40">
      <div className="py-3 grid grid-cols-[20px_minmax(0,1fr)_32px] gap-x-3 gap-y-3 sm:grid-cols-[20px_minmax(0,0.9fr)_minmax(0,1.4fr)_minmax(0,1.1fr)_32px] sm:gap-x-4 px-4 items-start">
        <span className="reading text-[12px] text-faint text-right h-10 sm:h-10 flex items-center justify-end">{n}</span>

        <label className="flex flex-col gap-1.5 min-w-0">
          <span className={label}>{t("team.topicCols.topic")}</span>
          {editable ? (
            <Input className="!h-10 text-[14px] font-medium" value={tp.name ?? ""} onChange={(e) => onChange({ name: e.target.value })} placeholder={t("team.topicName")} autoFocus={!tp.name} />
          ) : (
            <span className="min-h-10 flex items-center text-[14px] font-medium text-ink">{tp.name}</span>
          )}
        </label>

        <div className="col-start-3 row-start-1 sm:col-start-5 flex flex-col items-center gap-1">
          <button type="button" onClick={() => onChange({ open: false })} aria-expanded aria-label={t("common.close")} title={t("common.close")} className={`${rowBtn} text-muted hover:text-ink hover:bg-surface-2 mt-1`}>
            <ChevronDown size={16} strokeWidth={1.5} className="rotate-180" />
          </button>
          {editable && (
            <button type="button" onClick={onRemove} aria-label={t("team.removeTopic")} title={t("team.removeTopic")} className={`${rowBtn} text-faint hover:text-fading hover:bg-fading-soft`}>
              <Trash2 size={16} strokeWidth={1.5} />
            </button>
          )}
        </div>

        <label className="col-start-2 sm:col-start-3 sm:row-start-1 flex flex-col gap-1.5 min-w-0">
          <span className={label}>{t("team.topicCols.covers")}</span>
          {editable ? (
            <Textarea rows={3} className={area} value={tp.description ?? ""} onChange={(e) => onChange({ description: e.target.value })} placeholder={t("team.topicDesc")} />
          ) : (
            <span className="text-[13px] text-muted leading-5 sm:pt-2.5">{tp.description || "—"}</span>
          )}
        </label>

        <label className="col-start-2 sm:col-start-4 sm:row-start-1 flex flex-col gap-1.5 min-w-0">
          <span className={label}>{t("team.topicCols.phrases")}</span>
          {editable ? (
            <>
              <Textarea rows={3} className={area} value={tp.kw} onChange={(e) => onChange({ kw: e.target.value })} placeholder={t("team.phrasesAuto")} />
              <span className="text-[12px] text-faint">{t("team.commaHint")}</span>
            </>
          ) : kws.length ? (
            <span className="flex flex-wrap gap-1.5 sm:pt-2">
              {kws.map((k) => (
                <span key={k} className="rounded-md bg-surface-2 px-2 h-6 inline-flex items-center text-[12px] text-muted">{k}</span>
              ))}
            </span>
          ) : (
            <span className="text-[12px] text-faint sm:pt-2.5">{t("team.phrasesAuto")}</span>
          )}
        </label>
      </div>
    </li>
  );
}
