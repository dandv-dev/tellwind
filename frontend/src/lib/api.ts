export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(code);
  }
}

type Opts = { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal };

export async function api<T = unknown>(path: string, opts: Opts = {}): Promise<T> {
  const init: RequestInit = {
    method: opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET"),
    credentials: "same-origin",
    signal: opts.signal,
    headers: opts.body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: opts.form ?? (opts.body !== undefined ? JSON.stringify(opts.body) : undefined),
  };
  const res = await fetch(`/api${path}`, init);
  if (!res.ok) {
    let code = `http_${res.status}`;
    try {
      const j = await res.json();
      if (typeof j.detail === "string") code = j.detail;
      else if (Array.isArray(j.detail)) code = "validation_error";
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const wsPath = (wid: string, rest = "") => `/workspaces/${wid}${rest}`;
export const fileHref = (wid: string, fid: string, inline = false) =>
  `/api/workspaces/${wid}/files/${fid}/download${inline ? "?inline=1" : ""}`;
