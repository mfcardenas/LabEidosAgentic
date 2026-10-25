// Carga las specs, calcula su versión y las recarga solas si cambias los ficheros.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { config } from "./config.js";
import { RULES } from "./rules.js";

// Qué recibe y qué contexto tiene cada tipo de intent. Es parte del runtime, no de la app.
export const TIPOS = {
  listado: { params: "{filter?}", contexto: ["items", "count", "filter", "stats", "options"] },
  detalle: { params: "{id}", contexto: ["item", "stats", "options"] },
  alta: { params: "{prefill?}", contexto: ["item", "options"] },
  edicion: { params: "{id, prefill?}", contexto: ["item", "options"] },
  baja: { params: "{id}", contexto: ["item"] },
  libre: { params: "{key, filter?}", contexto: ["items", "count", "filter", "stats", "options"] }
};

const FILES = { app: "app.spec.json", design: "design.spec.json", catalog: "catalog.spec.json" };
let current = null;
let mtimes = "";

function stamp() {
  return Object.values(FILES).map(f => {
    try { return fs.statSync(path.join(config.specsDir, f)).mtimeMs; } catch { return 0; }
  }).join("|");
}

function check(specs) {
  const errs = [];
  const { app } = specs;
  if (!app.entidades || !Object.keys(app.entidades).length) errs.push("app.spec: no hay entidades");
  for (const [name, it] of Object.entries(app.intents || {})) {
    if (!TIPOS[it.tipo]) errs.push(`app.spec: el intent ${name} tiene un tipo desconocido (${it.tipo})`);
    if (!app.entidades[it.entidad]) errs.push(`app.spec: el intent ${name} apunta a la entidad ${it.entidad}, que no existe`);
  }
  if (!app.intents?.[app.inicio]) errs.push(`app.spec: inicio (${app.inicio}) no es un intent`);
  for (const [ename, e] of Object.entries(app.entidades || {})) {
    if (!e.campos?.[e.campoTitulo]) errs.push(`app.spec: ${ename}.campoTitulo no es un campo`);
    for (const r of e.reglas || []) if (!RULES[r.id]) errs.push(`app.spec: ${ename} usa la regla «${r.id}», que no está implementada en server/rules.js`);
  }
  return errs;
}

export function loadSpecs() {
  const s = stamp();
  if (current && s === mtimes) return current;
  try {
    const raw = {};
    for (const [k, f] of Object.entries(FILES)) raw[k] = fs.readFileSync(path.join(config.specsDir, f), "utf8");
    const specs = Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, JSON.parse(v)]));
    const errs = check(specs);
    if (errs.length) throw new Error(errs.join("\n"));
    const version = crypto.createHash("sha256").update(raw.app + raw.design + raw.catalog).digest("hex").slice(0, 8);
    const prev = current && current.version;
    current = { ...specs, version };
    mtimes = s;
    if (prev && prev !== version) console.log(`[specs] Cambiaron las specs: versión ${prev} → ${version}. Las plantillas anteriores dejan de usarse.`);
    return current;
  } catch (e) {
    if (!current) throw new Error(`No puedo cargar las specs:\n${e.message}`);
    console.error(`[specs] Error en las specs, sigo con la versión ${current.version}:\n${e.message}`);
    mtimes = s;
    return current;
  }
}

export function intentInfo(specs, name) {
  const it = specs.app.intents[name];
  if (!it) return null;
  return { name, ...it, entity: entityByName(specs, it.entidad), tipoInfo: TIPOS[it.tipo] };
}

export function entityByName(specs, name) {
  const e = specs.app.entidades[name];
  return e ? { ...e, nombreInterno: name } : null;
}

export function intentOfType(specs, entidad, tipo) {
  return Object.entries(specs.app.intents).find(([, it]) => it.entidad === entidad && it.tipo === tipo)?.[0] || null;
}
