import { useMutation, useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useParams } from "react-router-dom";
import { TopBar } from "../components/TopBar";
import { Button, ButtonLink, Card, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { useLogout, useMe } from "../lib/auth";
import type { Invitation } from "../lib/types";

export default function Invite() {
  const { token = "" } = useParams();
  const { t } = useTranslation();
  const nav = useNavigate();
  const { data: me, isLoading: meLoading } = useMe();
  const logout = useLogout();
  const q = useQuery({ queryKey: ["invite", token], queryFn: () => api<Invitation>(`/invitations/token/${token}`), retry: false });
  const accept = useMutation({
    mutationFn: (id: string) => api<{ workspace_id: string }>(`/invitations/${id}/accept`, { method: "POST" }),
    onSuccess: (r) => nav(`/app/w/${r.workspace_id}`),
  });
  const inv = q.data;
  const next = `/invite/${token}`;
  const match = me && inv && me.email.toLowerCase() === inv.email.toLowerCase();

  return (
    <div className="min-h-dvh">
      <TopBar />
      <main className="max-w-md mx-auto px-4 py-16">
        <Card className="p-7 flex flex-col gap-4">
          {q.isLoading || meLoading ? (
            <div className="flex justify-center py-6 text-muted"><Spinner /></div>
          ) : !inv || inv.status !== "pending" ? (
            <>
              <h1 className="text-[20px] font-medium text-ink">{t("invite.notFound")}</h1>
              <Link to="/app" className="text-accent font-medium">{t("topbar.workspaces")} →</Link>
            </>
          ) : (
            <>
              <h1 className="text-[28px] font-medium text-ink tracking-[-0.02em]">{t("invite.title")}</h1>
              <p className="text-ink">
                {t("invite.body", { workspace: inv.workspace?.name, role: t(`common.roles.${inv.role}`).toLowerCase() })}
              </p>
              <p className="text-[13px] text-muted">{inv.workspace?.subject}</p>
              <p className="text-[13px] text-faint">{t("invite.forEmail", { email: inv.email })}</p>
              {!me ? (
                <>
                  <p className="text-[14px] text-muted">{t("invite.loginToAccept")}</p>
                  <div className="flex gap-2">
                    <ButtonLink href={`/login?mode=signup&email=${encodeURIComponent(inv.email)}&next=${encodeURIComponent(next)}`}>{t("common.signup")}</ButtonLink>
                    <ButtonLink variant="secondary" href={`/login?email=${encodeURIComponent(inv.email)}&next=${encodeURIComponent(next)}`}>{t("common.login")}</ButtonLink>
                  </div>
                </>
              ) : match ? (
                <Button size="lg" loading={accept.isPending} onClick={() => accept.mutate(inv.id)}>
                  {t("common.accept")}
                </Button>
              ) : (
                <>
                  <p className="text-[14px] text-fading">{t("invite.wrongAccount", { email: me.email })}</p>
                  <Button variant="secondary" onClick={() => logout.mutate()}>{t("common.logout")}</Button>
                </>
              )}
            </>
          )}
        </Card>
      </main>
    </div>
  );
}
