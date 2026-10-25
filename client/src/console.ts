// Consola de supervisión: perfiles de modelo, construcción, intervenciones, artefactos con vista previa,
// trazabilidad y auditoría. Habla solo con el plano de control (/control) y reutiliza el renderizador.
import { h, render, type Ctx } from "./components";
import type { Manifest, ScreenDocument } from "./types";

type Json = Record<string, unknown>;
const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

async function call<T = Json>(method: string, url: string, body?: unknown): Promise<{ ok: boolean; body: T }> {
  const res = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  let json: unknown = {};
  try { json = await res.json(); } catch { /* sin cuerpo */ }
  return { ok: res.ok, body: json as T };
}

const state = { app: "", manifest: null as Manifest | null, selected: null as string | null };

const STATUS_TONE: Record<string, string> = {
  publicado: "good", candidato: "info", provisional: "info", pendiente_aprobacion: "warn", escalado: "bad", rechazado: "bad", desactualizado: "", retirado: "",
};
const badge = (text: string, tone = "") => h("span", { class: `g-badge sm ${tone}`, text });
const errorText = (b: unknown) => typeof (b as Json)?.detail === "string" ? String((b as Json).detail) : "No se ha podido completar.";

// ------------------------------------------------------------------ perfiles
async function loadProfiles() {
  const r = await call<{ active: string | null; profiles: Json[] }>("GET", "/control/profiles");
  $("#profiles").replaceChildren(...(r.body.profiles ?? []).map((p) => {
    const active = p.id === r.body.active;
    const result = h("p", { class: "meta", hidden: true });
    const models = Object.entries((p.models as Record<string, string>) ?? {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
    return h("article", { class: `card ${active ? "active" : ""}` },
      h("h3", null, String(p.label), active ? badge("En uso", "accent") : null, p.external ? badge("cloud · sin datos reales", "info") : null,
        p.configured ? null : badge("sin configurar", "warn")),
      h("span", { class: "meta", text: models || "—" }),
      h("div", { class: "btns" },
        h("button", { class: "g-btn primary", type: "button", disabled: active || !p.configured, onclick: async () => {
          const res = await call("PUT", "/control/profiles", { profile: p.id });
          if (!res.ok) alert(errorText(res.body));
          loadProfiles();
        } }, active ? "En uso" : "Usar"),
        h("button", { class: "g-btn", type: "button", disabled: !p.configured, onclick: async () => {
          result.hidden = false; result.textContent = "Probando…";
          const res = await call<Json>("POST", `/control/profiles/${p.id}/test`);
          result.textContent = res.body.ok ? `Responde en ${res.body.seconds ?? 0} s (${res.body.model})` : `Falla: ${res.body.error}`;
        } }, "Probar")),
      result);
  }));
}

// ------------------------------------------------------------------ aplicación
async function loadApp() {
  const [summary, manifest] = await Promise.all([
    call<Json[]>("GET", "/control/apps"),
    call<Manifest>("GET", `/api/apps/${state.app}`),
  ]);
  state.manifest = manifest.body;
  const s = summary.body.find((x) => x.app === state.app) ?? {};
  const spec = s.spec as Json | null;
  const screens = Object.entries((s.screens as Record<string, number>) ?? {}).map(([k, v]) => `${v} ${k}`).join(" · ");
  $("#appInfo").textContent = `${manifest.body.app.nombre} · especificación ${spec ? `${spec.version} (${spec.status})` : "sin construir"} · ${screens || "sin pantallas"}`;
  ($("#appLink") as HTMLAnchorElement).href = `/?app=${state.app}`;
  await Promise.all([loadInterventions(), loadArtifacts(), loadTrace(), loadAudit()]);
}

async function build() {
  const note = $("#buildNote");
  const btn = $("#buildBtn") as HTMLButtonElement;
  btn.disabled = true; note.hidden = false; note.textContent = "Reconciliando… (con un modelo real puede tardar)";
  const r = await call<Json>("POST", `/control/apps/${state.app}/build`, { mode: "lote" });
  btn.disabled = false;
  note.textContent = r.ok ? `${(r.body.changes as unknown[]).length} cambio(s) · ${(r.body.interventions as unknown[]).length} intervención(es) abierta(s)` : errorText(r.body);
  loadApp();
}

// ------------------------------------------------------------------ intervenciones
async function loadInterventions() {
  const r = await call<Json[]>("GET", `/control/interventions?app=${state.app}`);
  const box = $("#interventions");
  if (!r.body.length) { box.replaceChildren(h("p", { class: "meta", text: "Ninguna. El sistema no necesita decisiones ahora mismo." })); return; }
  box.replaceChildren(...r.body.map((it) => {
    const ev = (it.evidence ?? {}) as Json;
    const findings = ((ev.findings ?? ev.ambiguities ?? []) as Json[]).map((f) => h("li", { text: `[${f.severity}] ${f.message}` }));
    const changed = (ev.changed as string[] | undefined)?.length ? h("p", { class: "meta", text: `Cambia: ${(ev.changed as string[]).join(", ")}` }) : null;
    const decide = async (approve: boolean) => {
      const motive = approve ? "" : prompt("Motivo del rechazo (obligatorio):") ?? "";
      if (!approve && !motive.trim()) return;
      const res = await call("POST", `/control/interventions/${it.id}`, { decision: approve ? "aprobar" : "rechazar", motivo: motive });
      if (!res.ok) alert(errorText(res.body));
      loadApp();
    };
    const [kind, rest] = String(it.artifact).split(":");
    const key = (rest ?? "").split("@")[0]!;
    return h("article", { class: "card" },
      h("h3", null, badge(String(it.type), "warn"), String(it.artifact), badge(String(it.role))),
      h("p", { text: String(it.reason) }),
      changed,
      findings.length ? h("ul", null, findings) : null,
      h("div", { class: "btns" },
        h("button", { class: "g-btn primary", type: "button", onclick: () => decide(true) }, it.type === "H3" ? "Regenerar" : "Aprobar"),
        h("button", { class: "g-btn", type: "button", onclick: () => decide(false) }, "Rechazar"),
        kind === "screen" ? h("button", { class: "g-btn ghost", type: "button", onclick: () => select(key) }, "Revisar") : null));
  }));
}

// ------------------------------------------------------------------ artefactos
async function loadArtifacts() {
  const r = await call<Json[]>("GET", `/control/apps/${state.app}/artifacts`);
  const screens = r.body.filter((a) => a.kind === "screen");
  $("#artifacts").replaceChildren(...screens.map((a) => h("li", null,
    h("button", { type: "button", "aria-current": String(a.key === state.selected), onclick: () => select(String(a.key)) },
      h("span", { class: "k", text: `${a.key} · r${a.revision}` }),
      h("span", { class: "meta", text: String(a.title ?? "") }),
      h("span", { class: "row" }, badge(String(a.status), STATUS_TONE[String(a.status)]), a.risk ? badge(`riesgo ${a.risk}`) : null, a.route ? badge(String(a.route)) : null)))));
  if (state.selected) await select(state.selected, false);
}

async function select(key: string, scroll = true) {
  state.selected = key;
  document.querySelectorAll(".art-list button").forEach((b) => b.setAttribute("aria-current", String(b.querySelector(".k")?.textContent?.startsWith(`${key} `))));
  const [hist, prev] = await Promise.all([
    call<Json[]>("GET", `/control/apps/${state.app}/artifacts/screen/${key}`),
    call<{ document: ScreenDocument; data: Json; artifact: string; status: string }>("POST", `/control/apps/${state.app}/screens/${key}/preview`, {}),
  ]);
  const latest = hist.body[hist.body.length - 1] ?? {};
  const findings = ((latest.findings as Json[]) ?? []).filter((f) => f.severity !== "autofixed");
  const attempts = (((latest.provenance as Json)?.attempts as Json[]) ?? []);
  const json = h("pre", { class: "json", hidden: true, text: JSON.stringify(latest.document, null, 2) });
  const regenerate = async () => {
    const motive = prompt("¿Por qué regenerar? (queda en la auditoría)") ?? "";
    if (!motive.trim()) return;
    const res = await call("POST", `/control/apps/${state.app}/screens/${key}/regenerate`, { motivo: motive });
    if (!res.ok) alert(errorText(res.body));
    loadApp();
  };
  let preview: HTMLElement = h("p", { class: "meta", text: "Sin documento que mostrar." });
  if (prev.ok && state.manifest) {
    const view = state.manifest.views[key]!;
    const ctx: Ctx = {
      byId: new Map(prev.body.document.components.map((c) => [c.id, c])),
      data: prev.body.data,
      entity: state.manifest.entities[view.entidad]!,
      host: { navigate: () => undefined, command: async () => ({ ok: false }) },
      notify: () => undefined,
    };
    preview = h("div", { class: "preview", inert: true }, render(prev.body.document.root, ctx));
  }
  $("#detail").replaceChildren(
    h("div", { class: "bar" },
      h("b", { class: "mono", text: `${key} · r${latest.revision}` }), badge(String(latest.status), STATUS_TONE[String(latest.status)]),
      h("button", { class: "tbtn", type: "button", onclick: (e: Event) => { json.hidden = !json.hidden; (e.currentTarget as HTMLElement).textContent = json.hidden ? "Ver JSON" : "Ocultar JSON"; } }, "Ver JSON"),
      h("button", { class: "tbtn", type: "button", onclick: regenerate }, "Regenerar")),
    h("p", { class: "meta", text: `${attempts.length} intento(s) · perfil ${(latest.provenance as Json)?.profile ?? "—"} · ${(((latest.provenance as Json)?.requirements as string[]) ?? []).join(", ")}` }),
    findings.length ? h("ul", { class: "findings" }, findings.map((f) => h("li", { text: `[${f.severity}] ${f.code}: ${f.message}` }))) : h("p", { class: "meta", text: "Sin hallazgos." }),
    preview,
    h("p", { class: "meta", text: `Historial: ${hist.body.map((x) => `r${x.revision} ${x.status}`).join(" → ")}` }),
    json);
  if (scroll) $("#detail").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

// ------------------------------------------------------------------ trazabilidad y auditoría
async function loadTrace() {
  const r = await call<Json>("GET", `/control/apps/${state.app}/report`);
  const rows = (r.body.traceability as Json[] | undefined) ?? [];
  $("#trace").replaceChildren(rows.length
    ? h("div", { class: "g-table-wrap" }, h("table", { class: "g-table" },
        h("thead", null, h("tr", null, ["Requisito", "Implementado por", "Probado por", "Pantallas"].map((t) => h("th", { text: t })))),
        h("tbody", null, rows.map((t) => h("tr", null,
          h("td", { text: `${t.requirement} ${t.title}` }),
          h("td", { class: "email", text: (t.implementedBy as string[]).join(", ") }),
          h("td", null, (t.testedBy as string[]).length ? (t.testedBy as string[]).join(", ") : badge("sin pruebas", "bad")),
          h("td", null, (t.artifacts as Json[]).map((a) => badge(`${a.view} · ${a.status}`, STATUS_TONE[String(a.status)]))))))))
    : h("p", { class: "meta", text: "Aún no hay informe: construye la aplicación." }));
}

async function loadAudit() {
  const r = await call<Json[]>("GET", `/control/apps/${state.app}/audit`);
  $("#audit").replaceChildren(...r.body.slice(0, 30).map((a) => h("li", { text: `${a.ts} · ${a.actor} · ${a.action} ${JSON.stringify(a.detail)}` })));
}

async function boot() {
  $("#buildBtn").addEventListener("click", build);
  const apps = (await call<string[]>("GET", "/api/apps")).body;
  const sel = $("#appSelect") as HTMLSelectElement;
  sel.replaceChildren(...apps.map((a) => h("option", { value: a }, a)));
  const wanted = new URL(location.href).searchParams.get("app");
  state.app = wanted && apps.includes(wanted) ? wanted : apps[0] ?? "";
  sel.value = state.app;
  sel.addEventListener("change", () => { state.app = sel.value; state.selected = null; history.replaceState(null, "", `?app=${state.app}`); loadApp(); });
  await loadProfiles();
  if (state.app) await loadApp();
}

boot();
