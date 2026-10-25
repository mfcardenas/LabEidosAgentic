// Shell de aplicación: navegación, peticiones en lenguaje natural y vista técnica. No conoce ningún dominio.
import { api } from "./api";
import { h, render, type Ctx } from "./components";
import type { Manifest, ViewResponse } from "./types";

const $ = <T extends HTMLElement>(sel: string) => document.querySelector(sel) as T;

const state = {
  app: "",
  manifest: null as Manifest | null,
  current: null as { view: string; params: Record<string, unknown> } | null,
  history: [] as { view: string; params: Record<string, unknown> }[],
  last: null as ViewResponse | null,
  tech: localStorage.getItem("eidos.tech") === "1",
};

function notify(message: string) {
  const n = $("#note");
  n.textContent = message;
  n.hidden = !message;
}

function setBusy(busy: boolean) {
  $("#stage").classList.toggle("loading", busy);
  ($("#cmdInput") as HTMLInputElement).disabled = busy;
}

async function navigate(view: string, params: Record<string, unknown> = {}, push = true) {
  if (push && state.current) state.history.push(state.current);
  state.current = { view, params };
  notify("");
  setBusy(true);
  const res = await api.view(state.app, view, params);
  setBusy(false);
  if (!res.ok) {
    paint(null);
    $("#screen").replaceChildren(h("div", { class: "sys" }, h("h2", { text: res.status === 410 ? "Ya no existe" : "No se ha podido abrir" }),
      h("p", { text: typeof res.body.detail === "string" ? res.body.detail : "Inténtalo de nuevo en un momento." })));
    return;
  }
  paint(res.body);
}

function paint(res: ViewResponse | null) {
  state.last = res;
  $("#backBtn").hidden = !state.history.length;
  if (!res || !state.manifest) return;
  const view = state.manifest.views[res.view]!;
  const ctx: Ctx = {
    byId: new Map(res.document.components.map((c) => [c.id, c])),
    data: res.data,
    entity: state.manifest.entities[view.entidad]!,
    host: { navigate: (v, p) => navigate(v, p), command: async (cmd, input) => (await api.command(state.app, cmd, input)).body },
    notify,
  };
  $("#screen").replaceChildren(render(res.document.root, ctx) ?? h("p", { text: "No hay nada que mostrar." }));
  $("#techInfo").textContent = `${res.view} · ${res.source}${res.artifact ? ` · ${res.artifact}` : ""}`;
  $("#techTrace").replaceChildren(...(res.trace ?? []).map((t) =>
    h("li", null, h("b", { text: t.step }), ` ${t.text}`, t.risk ? h("span", { class: "g-badge", text: `riesgo ${t.risk} · ${t.route}` }) : null)));
  $("#techJson").textContent = JSON.stringify(res.document, null, 2);
}

async function ask(text: string) {
  if (!text.trim()) return;
  setBusy(true);
  const res = await api.ask(state.app, text, state.current);
  setBusy(false);
  if (res.body.view) await navigate(res.body.view, res.body.params ?? {});
  notify(res.body.reply ?? "");
}

function renderChips() {
  const box = $("#chips");
  box.replaceChildren(...(state.manifest?.app.sugerencias ?? []).map((s) =>
    h("button", { class: "chip", type: "button", onclick: () => (s.vista ? (state.history = [], navigate(s.vista, s.params ?? {}, false)) : ask(s.texto ?? "")) }, s.etiqueta)));
}

function setTech(on: boolean) {
  state.tech = on;
  localStorage.setItem("eidos.tech", on ? "1" : "0");
  document.body.classList.toggle("tech", on);
  $("#techBtn").setAttribute("aria-pressed", String(on));
}

async function loadApp(app: string) {
  state.app = app;
  state.history = [];
  const url = new URL(location.href);
  url.searchParams.set("app", app);
  history.replaceState(null, "", url);
  const res = await api.manifest(app);
  if (!res.ok) {
    $("#screen").replaceChildren(h("div", { class: "sys" }, h("h2", { text: "No se ha podido cargar la aplicación" })));
    return;
  }
  state.manifest = res.body;
  document.title = res.body.app.nombre;
  $("#appName").textContent = res.body.app.nombre;
  $("#specInfo").textContent = `spec ${res.body.version}${res.body.published ? "" : " · sin publicar"}`;
  renderChips();
  await navigate(res.body.app.inicio, {}, false);
}

async function boot() {
  setTech(state.tech);
  $("#techBtn").addEventListener("click", () => setTech(!state.tech));
  $("#backBtn").addEventListener("click", () => { const prev = state.history.pop(); if (prev) navigate(prev.view, prev.params, false); });
  $("#cmdForm").addEventListener("submit", (e) => { e.preventDefault(); const input = $("#cmdInput") as HTMLInputElement; const v = input.value; input.value = ""; ask(v); });
  const apps = (await api.apps()).body;
  const select = $("#appSelect") as HTMLSelectElement;
  select.replaceChildren(...apps.map((a) => h("option", { value: a }, a)));
  select.addEventListener("change", () => loadApp(select.value));
  const wanted = new URL(location.href).searchParams.get("app");
  const app = wanted && apps.includes(wanted) ? wanted : apps[0];
  if (app) {
    select.value = app;
    await loadApp(app);
  }
}

boot();
