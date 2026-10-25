import type { CommandResult, Manifest, ViewResponse } from "./types";

async function call<T>(method: string, url: string, body?: unknown): Promise<{ ok: boolean; status: number; body: T }> {
  const res = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json: unknown = {};
  try { json = await res.json(); } catch { /* respuesta vacía */ }
  return { ok: res.ok, status: res.status, body: json as T };
}

export const api = {
  apps: () => call<string[]>("GET", "/api/apps"),
  manifest: (app: string) => call<Manifest>("GET", `/api/apps/${encodeURIComponent(app)}`),
  view: (app: string, view: string, params: Record<string, unknown>) =>
    call<ViewResponse & { detail?: string }>("POST", `/api/apps/${encodeURIComponent(app)}/views/${encodeURIComponent(view)}`, { params }),
  command: (app: string, command: string, input: Record<string, unknown>) =>
    call<CommandResult>("POST", `/api/apps/${encodeURIComponent(app)}/commands/${encodeURIComponent(command)}`, { input }),
  ask: (app: string, text: string, current: unknown) =>
    call<{ reply: string; view: string | null; params?: Record<string, unknown> }>("POST", `/api/apps/${encodeURIComponent(app)}/ask`, { text, current }),
};
