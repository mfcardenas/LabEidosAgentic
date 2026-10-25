/* Eidos — administración: modelo activo y pantallas generadas. */
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
async function api(method, url, body) {
  try {
    const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body ? JSON.stringify(body) : undefined });
    let j = {}; try { j = await r.json(); } catch {}
    return { ok: r.ok, body: j };
  } catch { return { ok: false, body: { error: "No hay conexión con el servidor de Eidos." } }; }
}
const fmtDate = iso => new Date(iso).toLocaleString("es-ES", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

/* ------------------------------------------------------------------ modelo */
async function loadProfiles() {
  const r = await api("GET", "/api/admin/llm");
  const box = $("#profiles");
  if (!r.ok) { box.replaceChildren(h("p", { class: "meta", text: r.body.error || "No se pudo cargar." })); return; }
  box.replaceChildren(...r.body.profiles.map(profileCard));
}
function profileCard(p) {
  const result = h("p", { class: "result", hidden: true });
  const models = p.routerModel === p.composerModel ? p.routerModel : `${p.routerModel} · ${p.composerModel}`;
  return h("article", { class: `profile ${p.active ? "active" : ""}` },
    h("h3", null, p.label, p.active ? h("span", { class: "g-badge accent", text: "Activo" }) : null,
      !p.configured ? h("span", { class: "g-badge warn", text: "Sin configurar" }) : null),
    h("dl", null,
      h("dt", { text: "Servidor" }), h("dd", { text: p.baseUrl || "—" }),
      h("dt", { text: p.provider === "azure" ? "Deployment" : "Modelo" }), h("dd", { text: models || "—" }),
      p.apiVersion ? [h("dt", { text: "API" }), h("dd", { text: p.apiVersion })] : null,
      p.routerReasoning || p.composerReasoning ? [h("dt", { text: "Razonamiento" }), h("dd", { text: `${p.routerReasoning || "—"} / ${p.composerReasoning || "—"}` })] : null),
    !p.configured ? h("p", { class: "meta", text: "Rellena AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_API_KEY y AZURE_OPENAI_CHAT_DEPLOYMENT en .env y reinicia." }) : null,
    h("div", { class: "btns" },
      h("button", { class: "g-btn primary", type: "button", disabled: p.active || !p.configured, onclick: () => activate(p.id) }, p.active ? "En uso" : "Usar este modelo"),
      h("button", { class: "g-btn", type: "button", disabled: !p.configured, onclick: e => test(p.id, e.currentTarget, result) }, "Probar conexión")),
    result);
}
async function activate(id) {
  const r = await api("PUT", "/api/admin/llm", { profile: id });
  if (!r.ok) alert(r.body.error || "No se pudo cambiar el modelo.");
  loadProfiles();
}
async function test(id, btn, out) {
  btn.disabled = true; out.hidden = false; out.className = "result"; out.textContent = "Probando…";
  const r = await api("POST", "/api/admin/llm/test", { profile: id });
  btn.disabled = false;
  const ok = r.ok && r.body.ok;
  out.className = `result ${ok ? "ok" : "bad"}`;
  out.textContent = ok ? `Responde JSON en ${r.body.seconds.toFixed(1)} s` : (r.body.error || "No responde.");
}

/* ------------------------------------------------------------------ pantallas */
let screens = [], selected = null;
async function loadScreens() {
  const r = await api("GET", "/api/admin/screens");
  if (!r.ok) { $("#screenList").replaceChildren(h("li", { class: "meta", text: r.body.error || "No se pudo cargar." })); return; }
  screens = r.body.screens;
  $("#specInfo").textContent = `specs ${r.body.version} · ${screens.length} pantalla(s)`;
  $("#forgetAll").disabled = !screens.length;
  if (selected && !screens.some(d => d.key === selected)) selected = null;
  renderList();
  renderDetail();
}
function renderList() {
  const ul = $("#screenList");
  if (!screens.length) { ul.replaceChildren(h("li", { class: "meta", text: "Ninguna todavía. Se crean cuando alguien abre una vista en la app." })); return; }
  ul.replaceChildren(...screens.map(d => h("li", null,
    h("button", { type: "button", "aria-current": String(d.key === selected), onclick: () => { selected = d.key; renderList(); renderDetail(); } },
      h("span", { class: "k", text: d.key }),
      h("span", { class: "t", text: d.title || d.intent }),
      h("span", { class: "meta", text: `${d.model || "?"} · ${d.seconds ? d.seconds.toFixed(0) + " s" : "—"}${d.stale ? " · versión vieja" : ""}` })))));
}
function renderDetail() {
  const box = $("#screenDetail");
  const d = screens.find(x => x.key === selected);
  if (!d) { box.replaceChildren(h("p", { class: "meta", text: "Elige una pantalla para verla." })); return; }
  const src = `/?preview=1&intent=${encodeURIComponent(d.intent)}&params=${encodeURIComponent(JSON.stringify(d.previewParams || {}))}`;
  const json = h("pre", { class: "json", hidden: true, text: JSON.stringify(d.template, null, 2) });
  box.replaceChildren(...[
    h("div", { class: "bar" },
      h("b", { class: "mono", text: d.key }),
      d.stale ? h("span", { class: "g-badge warn", text: "Versión vieja de las specs" }) : h("span", { class: "g-badge good", text: "Vigente" }),
      h("button", { class: "tbtn", type: "button", onclick: e => { json.hidden = !json.hidden; e.currentTarget.textContent = json.hidden ? "Ver JSON" : "Ocultar JSON"; } }, "Ver JSON"),
      h("button", { class: "tbtn", type: "button", onclick: () => forget(d.key) }, "Olvidar")),
    h("p", { class: "meta", text: `${d.model || "?"} · ${d.seconds ? d.seconds.toFixed(1) + " s" : "—"} · ${d.nodes ?? "?"} nodos · ${fmtDate(d.createdAt)}${d.brief ? ` · «${d.brief}»` : ""}` }),
    d.fixes?.length ? h("div", null, h("p", { class: "meta", text: `El Guardián hizo ${d.fixes.length} corrección(es):` }), h("ul", { class: "fixes" }, d.fixes.map(f => h("li", { text: f })))) : null,
    d.stale ? h("p", { class: "meta", text: "Esta plantilla ya no se usa: las specs han cambiado desde que se generó." }) : h("iframe", { src, title: `Vista previa de ${d.key}`, loading: "lazy" }),
    json].filter(Boolean));
}
async function forget(key) {
  await api("DELETE", `/api/admin/screens/${encodeURIComponent(key)}`);
  loadScreens();
}
$("#forgetAll").addEventListener("click", async () => {
  if (!confirm("¿Olvidar todas las pantallas generadas? Se volverán a generar cuando se abran.")) return;
  await api("DELETE", "/api/admin/screens");
  loadScreens();
});

loadProfiles();
loadScreens();
