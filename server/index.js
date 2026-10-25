// Servidor HTTP de Eidos: sirve el runtime del navegador y la API de agentes y datos.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";
import { openStore } from "./store.js";
import { loadSpecs, entityByName, intentInfo } from "./specs.js";
import { makeData } from "./data.js";
import { makeRuntime } from "./runtime.js";
import { health, chatJSON, activeProfile, setActiveProfile, listProfiles, getProfile } from "./llm.js";

const specs0 = loadSpecs();
const store = openStore(config.dbFile);
const data = makeData(store);
const runtime = makeRuntime(store, data);

const savedProfile = store.getSetting("llmProfile");
if (savedProfile) {
  try { setActiveProfile(savedProfile); }
  catch (e) { console.warn(`[modelo] No se puede usar el perfil guardado «${savedProfile}»: ${e.message}`); }
}

// Carga los registros de ejemplo la primera vez
if (config.seed) {
  for (const name of Object.keys(specs0.app.entidades)) {
    const file = path.join(config.seedsDir, `${name}.json`);
    if (store.count(name) === 0 && fs.existsSync(file)) {
      const rows = JSON.parse(fs.readFileSync(file, "utf8"));
      for (const r of rows) store.insert(name, r);
      console.log(`[datos] Cargados ${rows.length} registros de ejemplo en ${name}`);
    }
  }
}

const MIME = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".json": "application/json; charset=utf-8", ".svg": "image/svg+xml", ".ico": "image/x-icon" };

function sendJSON(res, status, obj) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" });
  res.end(JSON.stringify(obj));
}

async function readBody(req) {
  let size = 0; const chunks = [];
  for await (const c of req) { size += c.length; if (size > 1e6) throw Object.assign(new Error("Cuerpo demasiado grande"), { status: 413 }); chunks.push(c); }
  if (!chunks.length) return {};
  try { return JSON.parse(Buffer.concat(chunks).toString("utf8")); }
  catch { throw Object.assign(new Error("JSON inválido"), { status: 400 }); }
}

// Respuesta en streaming: una línea JSON por evento (traza, nota, resultado…)
function streamTo(res) {
  res.writeHead(200, { "Content-Type": "application/x-ndjson; charset=utf-8", "Cache-Control": "no-store", "X-Accel-Buffering": "no" });
  const ctl = new AbortController();
  res.on("close", () => { if (!res.writableFinished) ctl.abort(); });
  const emit = ev => { if (!res.writableEnded && !ctl.signal.aborted) res.write(JSON.stringify(ev) + "\n"); };
  return { emit, signal: ctl.signal, end: () => { if (!res.writableEnded) res.end(); } };
}

function serveStatic(req, res, pathname) {
  const rel = pathname === "/" ? "index.html" : decodeURIComponent(pathname).replace(/^\/+/, "");
  const file = path.resolve(config.publicDir, rel);
  if (!file.startsWith(config.publicDir + path.sep) && file !== config.publicDir) { res.writeHead(403).end(); return; }
  fs.readFile(file, (err, buf) => {
    if (err) { res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" }).end("No encontrado"); return; }
    res.writeHead(200, { "Content-Type": MIME[path.extname(file)] || "application/octet-stream", "Cache-Control": "no-cache" });
    res.end(buf);
  });
}

function recordTrace(kind, text, status) { return [{ type: "trace", id: 1, kind, text, status, ms: 0 }]; }

function previewParams(specs, d) {
  const info = intentInfo(specs, d.intent);
  if (!info) return {};
  if (["detalle", "edicion", "baja"].includes(info.tipo)) return { id: data.all(info.entity)[0]?.id ?? "" };
  if (info.tipo === "libre") return { key: d.key.replace(/^custom\./, "") };
  return {};
}

async function handleAdmin(req, res, p) {
  if (req.method === "GET" && p === "/api/admin/llm") return sendJSON(res, 200, { profiles: listProfiles() });
  if (req.method === "PUT" && p === "/api/admin/llm") {
    const { profile } = await readBody(req);
    try { setActiveProfile(profile); } catch (e) { return sendJSON(res, 400, { error: e.message }); }
    store.setSetting("llmProfile", profile);
    console.log(`[modelo] Perfil activo: ${activeProfile().label}`);
    return sendJSON(res, 200, { profiles: listProfiles() });
  }
  if (req.method === "POST" && p === "/api/admin/llm/test") {
    const P = getProfile((await readBody(req)).profile);
    if (!P) return sendJSON(res, 404, { error: "Ese perfil no existe." });
    if (!P.configured) return sendJSON(res, 200, { ok: false, error: `${P.label} no está configurado en .env.` });
    try {
      const r = await chatJSON({ model: P.composerModel, reasoning: P.composerReasoning, profile: P, label: "check",
        prompt: 'Responde SOLO con este JSON, sin nada más: {"ok": true, "saludo": "hola desde Eidos"}' });
      return sendJSON(res, 200, { ok: true, seconds: r.seconds, value: r.value });
    } catch (e) { return sendJSON(res, 200, { ok: false, error: e.message }); }
  }
  if (req.method === "GET" && p === "/api/admin/screens") {
    const specs = loadSpecs();
    return sendJSON(res, 200, { version: specs.version, screens: store.listScreens().map(d => ({ ...d, stale: d.specVersion !== specs.version, previewParams: previewParams(specs, d) })) });
  }
  if (req.method === "DELETE" && p === "/api/admin/screens") {
    for (const d of store.listScreens()) store.deleteScreen(d.key);
    return sendJSON(res, 200, { ok: true });
  }
  if (req.method === "DELETE" && p.startsWith("/api/admin/screens/")) {
    store.deleteScreen(decodeURIComponent(p.slice("/api/admin/screens/".length)));
    return sendJSON(res, 200, { ok: true });
  }
  return sendJSON(res, 404, { error: "Ruta desconocida" });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const p = url.pathname;
  try {
    if (!p.startsWith("/api/")) return serveStatic(req, res, p);
    // Exigir JSON obliga a los navegadores a hacer preflight CORS: otra web no puede lanzar acciones aquí.
    if (req.method !== "GET" && !/^application\/json\b/i.test(req.headers["content-type"] || ""))
      return sendJSON(res, 415, { error: "Usa Content-Type: application/json" });
    if (p.startsWith("/api/admin/")) return await handleAdmin(req, res, p);

    if (req.method === "GET" && p === "/api/specs") {
      const s = loadSpecs();
      const P = activeProfile();
      return sendJSON(res, 200, { app: s.app, design: s.design, catalog: s.catalog, version: s.version,
        llm: { profile: P.id, provider: P.provider, routerModel: P.routerModel, composerModel: P.composerModel } });
    }
    if (req.method === "GET" && p === "/api/health") return sendJSON(res, 200, await health());
    if (req.method === "GET" && p === "/api/screens") return sendJSON(res, 200, runtime.listScreens());

    if (req.method === "POST" && p === "/api/navigate") {
      const body = await readBody(req);
      const s = streamTo(res);
      try { await runtime.navigate(body.nav, body, s.emit, s.signal); }
      catch (e) { console.error(e); s.emit({ type: "error", code: "internal", message: `Error interno: ${e.message}` }); }
      return s.end();
    }
    if (req.method === "POST" && p === "/api/ask") {
      const body = await readBody(req);
      const s = streamTo(res);
      try { await runtime.ask(String(body.text || "").slice(0, 1000), body.current || null, s.emit, s.signal); }
      catch (e) { console.error(e); s.emit({ type: "error", code: "internal", message: `Error interno: ${e.message}` }); }
      return s.end();
    }

    // Registros: /api/records/:entidad[/:id]
    const m = p.match(/^\/api\/records\/([^/]+)(?:\/([^/]+))?$/);
    if (m) {
      const E = entityByName(loadSpecs(), decodeURIComponent(m[1]));
      if (!E) return sendJSON(res, 404, { error: "Esa entidad no existe en la spec." });
      const id = m[2] && decodeURIComponent(m[2]);
      const titleOf = r => r?.[E.campoTitulo] ?? r?.id;
      if (req.method === "POST" && !id) {
        const r = data.create(E, await readBody(req));
        if (r.errors) return sendJSON(res, 422, { errors: r.errors, trace: recordTrace("data", `No se guarda: ${Object.values(r.errors).join(" ")}`, "fail") });
        return sendJSON(res, 201, { record: r.record, trace: recordTrace("data", `Alta de ${titleOf(r.record)}`, "done") });
      }
      if (req.method === "PUT" && id) {
        const r = data.update(E, id, await readBody(req));
        if (r.notFound) return sendJSON(res, 404, { error: `Ese ${E.etiqueta} ya no existe.` });
        if (r.errors) return sendJSON(res, 422, { errors: r.errors, trace: recordTrace("data", `No se guarda: ${Object.values(r.errors).join(" ")}`, "fail") });
        return sendJSON(res, 200, { record: r.record, trace: recordTrace("data", `Guardados los cambios de ${titleOf(r.record)}`, "done") });
      }
      if (req.method === "DELETE" && id) {
        const r = data.remove(E, id);
        if (r.notFound) return sendJSON(res, 404, { error: `Ese ${E.etiqueta} ya no existe.` });
        if (r.errors) return sendJSON(res, 409, { errors: r.errors, trace: recordTrace("data", `No se borra: ${r.errors._}`, "fail") });
        return sendJSON(res, 200, { record: r.record, trace: recordTrace("data", `Baja de ${titleOf(r.record)}`, "done") });
      }
    }
    sendJSON(res, 404, { error: "Ruta desconocida" });
  } catch (e) {
    if (!res.headersSent) sendJSON(res, e.status || 500, { error: e.message });
    else res.end();
    if (!e.status) console.error(e);
  }
});

server.listen(config.port, config.host, async () => {
  const url = `http://${config.host === "0.0.0.0" ? "localhost" : config.host}:${config.port}`;
  console.log(`\nEidos en marcha → ${url}`);
  console.log(`Specs versión ${specs0.version} · BD ${path.relative(process.cwd(), config.dbFile) || config.dbFile}`);
  const h = await health();
  const L = activeProfile();
  console.log(`Modelo activo: ${L.label} (cámbialo en ${url}/admin.html)`);
  if (!h.reachable) console.log(`\n⚠  No hay respuesta de ${L.baseUrl}. Arranca ${L.provider === "ollama" ? "Ollama (ollama serve)" : "tu servidor de modelos"} para que los agentes funcionen.\n   Las plantillas ya guardadas se siguen mostrando sin modelo.`);
  else if (h.missing.length) console.log(`\n⚠  Faltan modelos: ${h.missing.join(", ")}${L.provider === "ollama" ? `\n   Descárgalos con: ${h.missing.map(m => `ollama pull ${m}`).join(" && ")}` : ""}`);
  else console.log(`Modelos listos: Intérprete ${L.routerModel} (${L.routerReasoning || "por defecto"}) · Compositor ${L.composerModel} (${L.composerReasoning || "por defecto"})`);
  console.log("");
});

for (const sig of ["SIGINT", "SIGTERM"]) process.on(sig, () => { server.close(); store.close(); process.exit(0); });
