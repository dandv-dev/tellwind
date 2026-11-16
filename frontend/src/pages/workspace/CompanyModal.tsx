import { X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "motion/react";
import { useTranslation } from "react-i18next";
import { FileIcon, LinkIcon } from "../../brief/bits";
import { Spinner } from "../../components/ui";
import { api, fileHref } from "../../lib/api";
import { fmtDate } from "../../lib/format";
import { useWorkspace } from "./Layout";

interface CompanyDetail {
  id: string;
  name: string;
  aliases: string[];
  mentions: {
    item_id: string;
    title: string;
    url: string;
    source: string;
    source_type: string;
    file_id: string | null;
    date: string;
    alias: string;
    event_type: string;
    event: string;
    topics: string[];
  }[];
}

/** Everywhere a company is mentioned in the workspace, however sources spelled it. */
export function CompanyModal({ companyId, onClose }: { companyId: string | null; onClose: () => void }) {
  const ws = useWorkspace();
  const { t } = useTranslation();
  const q = useQuery({
    queryKey: ["company", ws.id, companyId],
    queryFn: () => api<CompanyDetail>(`/workspaces/${ws.id}/companies/${companyId}`),
    enabled: !!companyId,
  });
  const c = q.data;
  return (
    <AnimatePresence>
      {companyId && (
        <motion.div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center sm:p-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
          <div className="absolute inset-0 bg-[#0b1520]/45" onClick={onClose} />
          <motion.div
            initial={{ y: 30 }}
            animate={{ y: 0 }}
            exit={{ y: 30 }}
            className="relative w-full sm:max-w-xl max-h-[85dvh] overflow-y-auto rounded-t-[20px] sm:rounded-[20px] bg-bg border border-line shadow-pop p-6"
          >
            <button onClick={onClose} className="absolute right-4 top-4 w-8 h-8 rounded-[10px] hover:bg-surface-2 text-muted hover:text-ink flex items-center justify-center transition-colors duration-150 ease-out" aria-label={t("common.close")}><X size={16} strokeWidth={1.5} /></button>
            {!c ? (
              <div className="py-10 flex justify-center text-muted"><Spinner /></div>
            ) : (
              <>
                <div className="text-[12px] font-medium text-faint">{t("brief.companies")}</div>
                <h2 className="text-[20px] font-medium text-ink">{c.name}</h2>
                {c.aliases.length > 1 && (
                  <div className="flex flex-wrap gap-1.5 mt-2">
                    {c.aliases.map((a) => (
                      <span key={a} className="rounded-md bg-surface-2 px-2 py-0.5 text-[12px] text-muted">“{a}”</span>
                    ))}
                  </div>
                )}
                <p className="text-[13px] text-faint mt-3">{t("brief.mentions", { count: c.mentions.length })}</p>
                <ol className="mt-3 flex flex-col gap-3">
                  {c.mentions.map((m) => {
                    const href = m.file_id ? fileHref(ws.id, m.file_id, true) : m.url;
                    return (
                      <li key={m.item_id} className="rounded-xl border border-line bg-surface p-4">
                        <div className="text-[12px] text-faint flex flex-wrap items-center gap-x-2 gap-y-1">
                          <span className="reading">{fmtDate(m.date)}</span>
                          {m.event_type !== "other" && <span className="rounded-md bg-surface-2 px-1.5 h-5 inline-flex items-center text-muted">{m.event_type}</span>}
                          {m.topics.length > 0 && <span>{m.topics.join(", ")}</span>}
                        </div>
                        {m.event && <p className="mt-2 text-[14px] leading-snug text-ink font-medium">{m.event}</p>}
                        {/* the article the event comes from, as its citation */}
                        <a
                          href={href}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="mt-3 pt-3 border-t border-line flex items-start gap-2 text-[12px] text-muted hover:text-ink transition-colors duration-150 ease-out"
                        >
                          <span className="min-w-0 flex-1">
                            <span className="text-faint">{m.file_id ? <FileIcon size={12} className="inline -mt-0.5 mr-1" /> : null}{m.source}</span>
                            <span className="block mt-0.5">{m.title}</span>
                          </span>
                          <LinkIcon className="shrink-0 mt-0.5" />
                        </a>
                      </li>
                    );
                  })}
                </ol>
              </>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
