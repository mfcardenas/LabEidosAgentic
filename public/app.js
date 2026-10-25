/* Eidos — runtime del navegador.
   Shell determinista + Renderizador del catálogo. No contiene ninguna pantalla de la app:
   las recibe del servidor como plantillas JSON y las une con el contexto de datos. */
"use strict";

const $ = s => document.querySelector(s);
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  if (attrs) for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "text") el.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) el.append(k instanceof Node ? k : String(k));
  return el;
}
function since(iso) {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "hace un momento";
  if (s < 3600) return `hace ${Math.round(s / 60)} min`;
  if (s < 86400) return `hace ${Math.round(s / 3600)} h`;
  return `hace ${Math.round(s / 86400)} d`;
}
function fmtDate(v) { if (!v) return ""; const d = new Date(v); return isNaN(d) ? String(v) : d.toLocaleDateString("es-ES", { day: "numeric", month: "short", year: "numeric" }); }

/* ------------------------------------------------------------------ estado */
const S = {
  specs: null,
  current: null,      // {intent, params, key}
  history: [],
  shown: null,        // último evento result pintado
  busy: false, ctl: null, showJson: false,
  screens: [], streamSeq: 0, workingSince: 0, timer: null,
  tech: localStorage.getItem("eidos.tech") === "1"
};
const entity = name => S.specs.app.entidades[name];
const intentOfType = (ent, tipo) => Object.entries(S.specs.app.intents).find(([, it]) => it.entidad === ent && it.tipo === tipo)?.[0];

/* ------------------------------------------------------------------ API */
async function api(method, url, body) {
  try {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    let j = {}; try { j = await r.json(); } catch {}
    return { ok: r.ok, status: r.status, body: j };
  } catch { return { ok: false, status: 0, body: { error: "No hay conexión con el servidor de Eidos." } }; }
}
async function stream(url, body, onEvent) {
  S.ctl = new AbortController();
  const seq = ++S.streamSeq;
  try {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: S.ctl.signal });
    if (!res.ok || !res.body) { onEvent({ type: "error", message: `El servidor respondió con un error (${res.status}).` }); return; }
    const reader = res.body.getReader(); const dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const line = buf.slice(0, i); buf = buf.slice(i + 1);
        if (line.trim()) { try { onEvent({ ...JSON.parse(line), _seq: seq }); } catch (e) { console.error(e); } }
      }
    }
  } catch (e) {
    if (e.name === "AbortError") onEvent({ type: "cancelled" });
    else onEvent({ type: "error", message: "Se perdió la conexión con el servidor de Eidos." });
  }
}

/* ------------------------------------------------------------------ traza */
const KIND = { router: "Intérprete", cache: "Caché", composer: "Compositor", guard: "Guardián", data: "Datos" };
const traceEls = new Map();
function upsertTrace(ev) {
  const list = $("#steps");
  list.querySelector(".empty-trace")?.remove();
  const key = `${ev._seq ?? "x" + Math.random()}:${ev.id}`;
  let el = traceEls.get(key);
  if (!el) {
    el = { li: h("li"), ms: h("span", { class: "ms" }), what: h("div", { class: "what" }), det: h("div", { class: "det" }) };
    el.li.append(h("div", { class: "row1" }, h("span", { class: "who", text: KIND[ev.kind] || ev.kind }), el.ms), el.what, el.det);
    list.prepend(el.li);
    traceEls.set(key, el);
    while (list.children.length > 60) list.lastChild.remove();
  }
  el.li.className = `k-${ev.kind} ${ev.status === "run" ? "run" : ev.status === "fail" ? "fail" : ""}`;
  el.what.textContent = ev.text;
  if (ev.ms != null && ev.status !== "run") el.ms.textContent = ev.ms < 1000 ? `${ev.ms} ms` : `${(ev.ms / 1000).toFixed(1)} s`;
  el.det.replaceChildren();
  if (ev.details?.length) el.det.append(h("ul", null, ev.details.map(t => h("li", { text: t }))));
}

/* ------------------------------------------------------------------ renderizador */
function get(ctx, path) { return String(path).split(".").reduce((o, k) => (o == null ? undefined : o[k]), ctx); }
function show(v) { if (v === true) return "Sí"; if (v === false) return "No"; if (v == null) return ""; if (Array.isArray(v)) return String(v.length); if (typeof v === "object") return ""; return String(v); }
function interp(s, ctx) {
  if (typeof s !== "string") return s;
  const whole = s.match(/^\{\{\s*([\w.]+)\s*\}\}$/);
  if (whole) return get(ctx, whole[1]);
  return s.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, p) => show(get(ctx, p)));
}
function val(v, ctx) {
  if (v && typeof v === "object" && !Array.isArray(v) && typeof v.$bind === "string") return get(ctx, v.$bind);
  return typeof v === "string" ? interp(v, ctx) : v;
}
function deep(v, ctx) {
  if (Array.isArray(v)) return v.map(x => deep(x, ctx));
  if (v && typeof v === "object") { if (typeof v.$bind === "string") return get(ctx, v.$bind); const o = {}; for (const k in v) o[k] = deep(v[k], ctx); return o; }
  return typeof v === "string" ? interp(v, ctx) : v;
}
function cond(when, ctx) {
  if (!when) return true;
  const neg = when.startsWith("!");
  const r = get(ctx, neg ? when.slice(1) : when);
  const t = Array.isArray(r) ? r.length > 0 : !!r;
  return neg ? !t : t;
}
function badge(text, tone) { return h("span", { class: `g-badge ${tone || ""}`, text: show(text) }); }
function fieldOf(expr) { return typeof expr === "string" ? (expr.match(/^\{\{\s*\w+\.(\w+)\s*\}\}$/) || [])[1] : null; }

function fmtCell(value, format, field, E) {
  const def = E?.campos?.[field];
  if (!format || format === "text") {
    if (def?.tipo === "enum") format = "badge";
    else if (def?.tipo === "booleano") format = "status";
    else if (def?.tipo === "fecha") format = "date";
  }
  switch (format) {
    case "badge": {
      const opt = def?.valores?.find(x => x.valor === value);
      return badge(opt ? opt.etiqueta : value, opt?.tono);
    }
    case "status": return value ? badge(def?.si || "Sí", "good") : badge(def?.no || "No", "");
    case "date": return document.createTextNode(fmtDate(value));
    case "person": {
      const name = show(value);
      const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0].toUpperCase()).join("");
      const hue = [...name].reduce((a, c) => a + c.charCodeAt(0), 0) % 5;
      return h("span", { class: "g-person" }, h("span", { class: `av c${hue}`, "aria-hidden": "true", text: initials }), h("span", { text: name }));
    }
    default: return document.createTextNode(show(value));
  }
}

function render(n, ctx, E) {
  if (!n || !cond(n.when, ctx)) return null;
  const kids = () => (n.children || []).map(c => render(c, ctx, E));
  switch (n.type) {
    case "Screen": return h("div", { class: "g-screen" },
      h("div", { class: "g-head" },
        h("div", null, h("h2", { text: show(val(n.title, ctx)) }), n.subtitle ? h("p", { class: "sub", text: show(val(n.subtitle, ctx)) }) : null),
        (n.actions || []).length ? h("div", { class: "g-actions" }, n.actions.map(b => render(b, ctx, E))) : null),
      h("div", { class: "g-body" }, kids()));
    case "Section": return h("section", { class: "g-section" }, n.title ? h("h3", { text: show(val(n.title, ctx)) }) : null, kids());
    case "Row": return h("div", { class: "g-row" }, kids());
    case "Text": return h("p", { class: `g-text ${n.variant || "body"}`, text: show(val(n.value, ctx)) });
    case "Stat": return h("div", { class: `g-stat ${n.tone || ""}` },
      h("span", { class: "l", text: show(val(n.label, ctx)) }), h("span", { class: "v", text: show(val(n.value, ctx)) }),
      n.hint ? h("span", { class: "hnt", text: show(val(n.hint, ctx)) }) : null);
    case "Badge": {
      const field = fieldOf(n.value);
      const v = val(n.value, ctx);
      if (field && E?.campos?.[field]) return h("div", null, fmtCell(v, "badge", field, E));
      return h("div", null, badge(v, n.tone));
    }
    case "Alert": return h("div", { class: `g-alert ${n.tone || "info"}`, role: "status" }, n.title ? h("b", { text: show(val(n.title, ctx)) }) : null, show(val(n.text, ctx)));
    case "Empty": return h("div", { class: "g-empty" }, h("b", { text: show(val(n.title, ctx)) }), h("p", { text: show(val(n.text, ctx)) }), n.button ? render(n.button, ctx, E) : null);
    case "Button": return h("button", { class: `g-btn ${n.variant}`, type: "button", onclick: () => perform(n.action, ctx) }, show(val(n.label, ctx)));
    case "KeyValue": return h("dl", { class: "g-kv" }, (n.items || []).map(it => {
      const field = fieldOf(it.value);
      return [h("dt", { text: show(val(it.label, ctx)) }), h("dd", null, fmtCell(val(it.value, ctx), it.format, field, E))];
    }));
    case "BarList": {
      const items = (val(n.items, ctx) || []).filter(x => x && typeof x === "object");
      const max = Math.max(1, ...items.map(x => +x.value || 0));
      return h("div", { class: "g-section" }, n.title ? h("h3", { text: show(val(n.title, ctx)) }) : null,
        h("div", { class: "g-bars" }, items.map(x => h("div", { class: "b" },
          h("span", { text: show(x.label) }),
          h("div", { class: "track" }, h("div", { class: "fill", style: `width:${((+x.value || 0) / max) * 100}%` })),
          h("span", { class: "n", text: show(x.value) })))));
    }
    case "Table": {
      const rows = val(n.rows, ctx);
      const list = Array.isArray(rows) ? rows : [];
      if (!list.length) return h("p", { class: "g-text muted", text: show(val(n.empty, ctx)) || "No hay nada que mostrar." });
      return h("div", { class: "g-table-wrap" }, h("table", { class: "g-table" },
        h("thead", null, h("tr", null, n.columns.map(c => h("th", { text: c.label })))),
        h("tbody", null, list.map(row => {
          const rctx = { ...ctx, row };
          const tr = h("tr", n.rowAction ? { class: "click", tabindex: "0", role: "button" } : null,
            n.columns.map(c => h("td", { "data-label": c.label, class: c.format === "email" ? "email" : null }, h("span", { class: "cell" }, fmtCell(row[c.field], (!c.format || c.format === "text") && c.field === E?.campoTitulo ? "person" : c.format, c.field, E)))));
          if (n.rowAction) {
            tr.addEventListener("click", () => perform(n.rowAction, rctx));
            tr.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); perform(n.rowAction, rctx); } });
          }
          return tr;
        }))));
    }
    case "Form": return renderForm(n, ctx, E);
  }
  return null;
}

function renderForm(n, ctx, E) {
  const item = ctx.item || {};
  const isCreate = S.shown?.tipo === "alta";
  const errEls = {}, wrapEls = {};
  const form = h("form", { class: "g-form", novalidate: true });
  for (const f of n.fields) {
    const def = E.campos[f.field];
    if (!def) continue;
    const id = `f-${f.field}`;
    let input;
    if (def.tipo === "enum") input = h("select", { id, name: f.field }, def.valores.map(v => h("option", { value: v.valor, selected: item[f.field] === v.valor }, v.etiqueta)));
    else if (def.tipo === "booleano") input = h("input", { id, name: f.field, type: "checkbox", checked: !!item[f.field] });
    else input = h("input", { id, name: f.field, type: def.tipo === "email" ? "email" : "text", value: item[f.field] ?? "", maxlength: def.max || 120, autocomplete: "off" });
    const err = h("span", { class: "err", role: "alert" });
    errEls[f.field] = err;
    const help = f.help ? h("span", { class: "help", text: f.help }) : null;
    const wrap = def.tipo === "booleano"
      ? h("div", { class: "g-field" }, h("label", { class: "g-switch", for: id }, input, f.label), help, err)
      : h("div", { class: "g-field" }, h("label", { for: id, text: f.label + (def.requerido ? " *" : "") }), input, help, err);
    wrapEls[f.field] = wrap;
    form.append(wrap);
  }
  const formErr = h("div", { class: "g-alert danger", role: "alert", hidden: true });
  const submit = h("button", { class: "g-btn primary", type: "submit" }, show(val(n.submit.label, ctx)));
  form.append(formErr, h("div", { class: "btns" }, submit,
    n.cancel ? h("button", { class: "g-btn ghost", type: "button", onclick: () => perform(n.cancel.action, ctx) }, show(val(n.cancel.label, ctx))) : null));

  form.addEventListener("submit", async e => {
    e.preventDefault();
    const values = {};
    for (const f of n.fields) { const el = form.elements[f.field]; if (el) values[f.field] = el.type === "checkbox" ? el.checked : el.value; }
    submit.disabled = true;
    const ent = S.shown.entity;
    const r = isCreate
      ? await api("POST", `/api/records/${encodeURIComponent(ent)}`, values)
      : await api("PUT", `/api/records/${encodeURIComponent(ent)}/${encodeURIComponent(item.id)}`, values);
    submit.disabled = false;
    (r.body.trace || []).forEach(t => upsertTrace(t));
    for (const k in errEls) { errEls[k].textContent = r.body.errors?.[k] || ""; wrapEls[k].classList.toggle("bad", !!r.body.errors?.[k]); }
    const general = r.body.errors ? Object.entries(r.body.errors).filter(([k]) => !errEls[k]).map(([, v]) => v) : [];
    if (!r.ok) {
      formErr.hidden = !(general.length || r.body.error);
      formErr.textContent = general.join(" ") || r.body.error || "";
      return;
    }
    const target = intentOfType(ent, S.specs.app.flujos[isCreate ? "alta" : "edicion"]);
    go({ intent: target, params: { id: r.body.record.id } }, { push: false });
  });
  return form;
}

async function perform(action, ctx) {
  if (S.busy || !action) return;
  const a = deep(action, ctx);
  if (a.type === "navigate") return go({ intent: a.intent, params: a.params || {} });
  if (a.type === "ask") return ask(a.text);
  if (a.type === "delete") {
    const ent = S.shown.entity;
    const r = await api("DELETE", `/api/records/${encodeURIComponent(ent)}/${encodeURIComponent(a.id)}`);
    (r.body.trace || []).forEach(t => upsertTrace(t));
    if (!r.ok) { showNote("Datos", r.body.errors?._ || r.body.error || "No se ha podido dar de baja."); return; }
    S.history = [];
    go({ intent: intentOfType(ent, S.specs.app.flujos.baja), params: {} }, { push: false });
  }
}

/* ------------------------------------------------------------------ pintado */
function handle(ev) {
  switch (ev.type) {
    case "trace": upsertTrace(ev); break;
    case "note": showNote(ev.who, ev.error && !S.tech ? "No he podido entenderte ahora mismo. Inténtalo de nuevo en un momento." : ev.text); break;
    case "nav": if (S.current) S.history.push(S.current); S.current = { ...ev.nav }; updateBar(); break;
    case "working": S.current = ev.nav; paintWorking(ev.text); break;
    case "result": S.current = ev.nav; paint(ev); refreshScreens(); break;
    case "missing": S.current = ev.nav; if (S.preview) paintSys("Sin plantilla vigente", "Esta vista no tiene plantilla para la versión actual de las specs."); else paintWelcome(); break;
    case "gone": S.current = ev.nav; paintSys("Ese registro ya no existe", ev.message, "Ir al inicio", goHome); break;
    case "error": paintError(ev.message); break;
    case "cancelled": if (!S.shown || S.shown.nav.key !== S.current?.key) paintSys("Has cancelado la petición", null, S.current ? "Volver a intentarlo" : null, retry); break;
  }
}
function retry() { const nav = S.current; if (nav) go({ intent: nav.intent, params: nav.params }, { push: false }); }
function paint(ev) {
  stopTimer();
  S.shown = ev;
  const E = entity(ev.entity);
  $("#screen").replaceChildren(render(ev.screen.template, ev.context, E) || h("p", { text: "No hay nada que mostrar." }));
  const stage = $("#stage");
  stage.classList.remove("materialize", "loading");
  if (!ev.fromCache) { void stage.offsetWidth; stage.classList.add("materialize"); }
  $("#screenJson").textContent = JSON.stringify(ev.screen.template, null, 2);
  $("#screenJson").hidden = !S.showJson;
  updateBar();
}
function paintSys(title, text, btnLabel, onClick) {
  stopTimer();
  S.shown = null;
  $("#stage").classList.remove("loading");
  $("#screen").replaceChildren(h("div", { class: "sys" }, h("h2", { text: title }), text ? h("p", { text }) : null,
    btnLabel ? h("button", { class: "g-btn primary", type: "button", onclick: onClick }, btnLabel) : null));
  $("#screenJson").hidden = true;
  updateBar();
}
function paintError(reason) {
  const text = S.tech && reason ? reason : "Algo ha fallado. Inténtalo de nuevo en un momento.";
  paintSys("No se ha podido abrir", text, S.current ? "Volver a intentarlo" : null, retry);
}
// Portada: el primer clic es el que despierta a los agentes, así abrir la página no llama al modelo.
function paintWelcome() {
  const app = S.specs.app, nav = S.current;
  const it = app.intents[nav.intent], E = entity(it.entidad);
  const examples = (app.sugerencias || []).filter(s => s.texto).slice(0, 2).map(s => `«${s.texto}»`).join(" o ");
  paintSys(app.nombre.replace(/^Eidos\s*/, "") || app.nombre, app.proposito,
    it.tipo === "listado" ? `Ver ${E.plural}` : "Empezar", retry);
  const box = $("#screen .sys");
  if (examples) box.insertBefore(h("p", { text: `Empieza por aquí o escribe abajo lo que necesitas, por ejemplo ${examples}.` }), box.querySelector("button"));
  if (S.tech) box.append(h("p", { class: "mono", text: `«${nav.intent}» aún no tiene plantilla: al pulsar, el Compositor la genera y queda en caché.` }));
}
function workingLabel(nav) {
  const it = S.specs?.app.intents[nav?.intent];
  const E = it && entity(it.entidad);
  if (!E) return "Cargando";
  return { listado: `Cargando ${E.plural}`, detalle: "Abriendo la ficha", alta: `Preparando el alta de ${E.etiqueta}`,
    edicion: "Preparando la edición", baja: "Preparando la baja", libre: "Preparando el resumen" }[it.tipo] || "Cargando";
}
function paintWorking(text) {
  S.shown = null;
  $("#stage").classList.remove("loading");
  const el = h("span", { class: "elapsed", text: "0 s" });
  $("#screen").replaceChildren(h("div", { class: "sys" },
    h("div", { class: "working" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")), S.tech ? text : workingLabel(S.current)),
    h("p", { text: S.tech
      ? "Con un modelo local la primera vez puede tardar entre unos segundos y un par de minutos. Las siguientes, la plantilla sale de la caché."
      : "La primera vez puede tardar un poco; después es inmediato." }),
    el,
    h("div", { class: "skel" }, h("div", { style: "width:35%" }), h("div"), h("div", { style: "width:80%" }), h("div", { style: "width:60%" }))));
  $("#screenJson").hidden = true;
  stopTimer();
  S.workingSince = Date.now();
  S.timer = setInterval(() => { el.textContent = `${Math.round((Date.now() - S.workingSince) / 1000)} s`; }, 1000);
  updateBar();
}
function stopTimer() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }
function showNote(who, text) { const n = $("#note"); n.replaceChildren(...(S.tech ? [h("b", { text: who })] : []), h("span", { text })); n.hidden = false; }

/* ------------------------------------------------------------------ navegación */
async function go(nav, { push = true, regenerate = false, brief = null, title = null, auto = true } = {}) {
  if (S.busy || !nav?.intent) return;
  if (push && S.current) S.history.push(S.current);
  S.current = { intent: nav.intent, params: nav.params || {}, key: null };
  S.showJson = false;
  $("#note").hidden = true;
  $("#stage").classList.add("loading");
  setBusy(true);
  await stream("/api/navigate", { nav, regenerate, brief, title, auto }, handle);
  $("#stage").classList.remove("loading");
  setBusy(false);
}
async function ask(text) {
  text = String(text || "").trim();
  if (!text || S.busy) return;
  $("#note").hidden = true;
  $("#stage").classList.add("loading");
  setBusy(true);
  await stream("/api/ask", { text, current: S.current }, handle);
  $("#stage").classList.remove("loading");
  setBusy(false);
}
function goHome() { S.history = []; go({ intent: S.specs.app.inicio, params: {} }, { push: false }); }

/* ------------------------------------------------------------------ shell */
function updateBar() {
  $("#backBtn").hidden = !S.history.length;
  const prov = $("#prov");
  prov.replaceChildren();
  if (S.current?.key || S.current?.intent) prov.append(h("span", { class: "key", text: S.current.key || S.current.intent }));
  if (S.shown) prov.append(
    h("span", { class: `pill ${S.shown.fromCache ? "hit" : "new"}`, text: S.shown.fromCache ? "desde caché" : "recién generada" }),
    h("span", { text: `${since(S.shown.screen.createdAt)}${S.shown.screen.model ? ` · ${S.shown.screen.model}` : ""}${S.shown.screen.seconds ? ` · ${S.shown.screen.seconds.toFixed(0)} s` : ""}` }));
  $("#jsonBtn").hidden = !S.shown;
  $("#jsonBtn").textContent = S.showJson ? "Ocultar JSON" : "Ver JSON";
  $("#regenBtn").hidden = !S.shown;
  $("#regenBtn").disabled = S.busy;
  $("#backBtn").disabled = S.busy;
}
function setBusy(b) {
  S.busy = b;
  $("#sendBtn").hidden = b; $("#stopBtn").hidden = !b; $("#cmdInput").disabled = b;
  document.querySelectorAll(".chip").forEach(c => { c.disabled = b; });
  updateBar();
}
function renderChips() {
  const box = $("#chips");
  box.replaceChildren();
  for (const s of S.specs.app.sugerencias || []) {
    box.append(h("button", { class: "chip", type: "button", disabled: S.busy, onclick: () => {
      if (s.intent) { S.history = []; go({ intent: s.intent, params: s.params || {} }, { push: false }); }
      else ask(s.texto);
    } }, s.etiqueta));
  }
  for (const d of S.screens.filter(d => d.key.startsWith("custom.") && !d.stale)) {
    box.append(h("button", { class: "chip saved-view", type: "button", disabled: S.busy, title: S.tech ? "Vista guardada: sale de la caché sin llamar al modelo" : null,
      onclick: () => go({ intent: d.intent, params: { key: d.key.replace(/^custom\./, "") } }) }, d.title || d.key));
  }
}
async function refreshScreens() {
  if (S.preview) return;
  const r = await api("GET", "/api/screens");
  if (r.ok) S.screens = r.body;
  renderChips();
}
async function checkHealth() {
  const st = $("#status"), label = st.querySelector("span");
  st.classList.remove("ok", "warn", "bad"); label.textContent = "Comprobando modelo…";
  const r = await api("GET", "/api/health");
  const hh = r.body || {};
  const banner = $("#banner");
  banner.hidden = true;
  if (!r.ok) { st.classList.add("bad"); label.textContent = "Sin servidor"; return; }
  if (!S.tech && (!hh.reachable || hh.missing?.length)) {
    st.classList.add("bad");
    banner.replaceChildren("El asistente no está disponible ahora mismo. Puedes seguir usando lo que ya hayas abierto antes.");
    banner.hidden = false;
  } else if (!hh.reachable) {
    st.classList.add("bad"); label.textContent = hh.provider === "ollama" ? "Ollama no responde" : "Modelo no responde";
    banner.replaceChildren(`No hay respuesta de ${hh.baseUrl}. `, hh.provider === "ollama" ? h("span", null, "Abre Ollama o ejecuta ", h("code", { text: "ollama serve" }), ". ") : "Arranca tu servidor de modelos. ", "Las plantillas ya guardadas siguen funcionando.");
    banner.hidden = false;
  } else if (hh.missing?.length) {
    st.classList.add("warn"); label.textContent = `Falta ${hh.missing[0]}`;
    if (hh.provider === "ollama") banner.replaceChildren("Falta descargar el modelo. Ejecuta ", h("code", { text: hh.missing.map(m => `ollama pull ${m}`).join(" && ") }), " y pulsa el indicador de arriba para volver a comprobarlo.");
    else banner.replaceChildren(`Tu servidor no tiene cargado ${hh.missing.join(", ")}. Cárgalo o cambia ROUTER_MODEL y COMPOSER_MODEL en .env.`);
    banner.hidden = false;
  } else {
    st.classList.add("ok");
    label.textContent = hh.routerModel === hh.composerModel ? `${hh.composerModel} · listo` : `${hh.routerModel} + ${hh.composerModel}`;
  }
}
function renderSpecs() {
  const items = [
    { name: "specs/app.spec.json", what: "El dominio: entidades con sus campos, reglas y métricas; los intents (qué pantallas pueden existir) y los flujos entre ellas.", readers: "Intérprete · Compositor · Guardián · Datos", data: S.specs.app },
    { name: "specs/design.spec.json", what: "Cómo debe sentirse la app: tono de voz y reglas de composición que el Compositor sigue y el Guardián hace cumplir.", readers: "Compositor · Guardián", data: S.specs.design },
    { name: "specs/catalog.spec.json", what: "El vocabulario visual: los únicos componentes y acciones que existen. Es el contrato entre la IA y el Renderizador.", readers: "Compositor · Guardián · Renderizador", data: S.specs.catalog }
  ];
  $("#specList").replaceChildren(...items.map(s => h("article", { class: "spec" },
    h("header", null, h("code", { text: s.name }), h("span", { class: "readers", text: `Lo leen: ${s.readers}` })),
    h("p", { text: s.what }),
    h("pre", { text: JSON.stringify(s.data, null, 2) }))));
}

/* ------------------------------------------------------------------ arranque */
document.querySelectorAll(".tabs button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", String(x === b)));
  for (const t of ["app", "specs", "arq"]) $("#tab-" + t).hidden = t !== b.dataset.tab;
  $("#cmd").hidden = b.dataset.tab !== "app";
  window.scrollTo(0, 0);
}));
$("#backBtn").addEventListener("click", () => { if (S.busy) return; const prev = S.history.pop(); if (prev) go({ intent: prev.intent, params: prev.params }, { push: false }); });
$("#jsonBtn").addEventListener("click", () => { S.showJson = !S.showJson; $("#screenJson").hidden = !S.showJson; updateBar(); });
$("#regenBtn").addEventListener("click", () => {
  if (S.busy || !S.current) return;
  go({ intent: S.current.intent, params: S.current.params }, { push: false, regenerate: true, brief: S.shown?.screen.brief, title: S.shown?.screen.title });
});
$("#stopBtn").addEventListener("click", () => S.ctl?.abort());
function setTech(on) {
  S.tech = on;
  localStorage.setItem("eidos.tech", on ? "1" : "0");
  document.body.classList.toggle("tech", on);
  $("#techBtn").setAttribute("aria-pressed", String(on));
  if (!on) $("#t-app").click();
}
setTech(S.tech);
$("#techBtn").addEventListener("click", () => { setTech(!S.tech); if (S.specs) { checkHealth(); renderChips(); } });
$("#status").addEventListener("click", checkHealth);
$("#cmdForm").addEventListener("submit", e => { e.preventDefault(); const v = $("#cmdInput").value; $("#cmdInput").value = ""; ask(v); });

(async function boot() {
  const r = await api("GET", "/api/specs");
  if (!r.ok) { paintSys("No hay conexión con el servidor", r.body.error || "Arranca Eidos con npm start y recarga la página."); return; }
  S.specs = r.body;
  $("#appName").textContent = S.specs.app.nombre.replace(/^Eidos\s*/, "").toLowerCase();
  $("#specVer").textContent = `spec ${S.specs.version}`;
  // Vista previa de solo lectura que usa /admin.html: sin cabecera, sin barra y sin clics.
  const qs = new URLSearchParams(location.search);
  if (qs.has("preview")) {
    S.preview = true;
    document.body.classList.add("preview");
    let params = {};
    try { params = JSON.parse(qs.get("params") || "{}"); } catch {}
    go({ intent: qs.get("intent"), params }, { push: false, auto: false });
    return;
  }
  renderSpecs();
  await refreshScreens();
  checkHealth();
  go({ intent: S.specs.app.inicio, params: {} }, { push: false, auto: false });
})();
