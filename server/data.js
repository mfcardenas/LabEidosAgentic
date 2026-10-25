// Agente de Datos — determinista. Filtra, calcula métricas, prepara el contexto de cada
// pantalla y valida/escribe registros con las reglas de la spec. Ningún LLM pasa por aquí.
import crypto from "node:crypto";
import { RULES } from "./rules.js";

const lower = s => String(s ?? "").toLowerCase();
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function enumValues(def) { return (def.valores || []).map(v => v.valor); }
function enumLabel(def, v) { return def.valores?.find(x => x.valor === v)?.etiqueta ?? v; }

// El Intérprete a veces escribe "no", "Admin" o "editores": se aceptan si no hay ambigüedad.
function toBool(v) {
  if (typeof v === "boolean") return v;
  const s = lower(v).trim();
  if (["true", "sí", "si", "yes", "1"].includes(s)) return true;
  if (["false", "no", "0"].includes(s)) return false;
  return undefined;
}
function toEnum(def, v) {
  if (typeof v !== "string") return undefined;
  const s = lower(v).trim();
  const hit = def.valores.find(x => lower(x.valor) === s || lower(x.etiqueta) === s)
    || def.valores.find(x => lower(x.valor) === s.replace(/e?s$/, "") || lower(x.etiqueta) === s.replace(/e?s$/, ""));
  return hit?.valor;
}
// "activo=no, rol=editor" → {activo:"no", rol:"editor"}
function parsePairs(f) {
  if (typeof f !== "string") return f;
  const o = {};
  for (const part of f.split(/\s*(?:,|;|&|\by\b)\s*/)) {
    const m = part.match(/^\s*(\w+)\s*[=:]\s*(.+?)\s*$/);
    if (m) o[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return o;
}

export function makeData(store) {
  function all(E) {
    const ord = E.orden || E.campoTitulo;
    return store.list(E.nombreInterno).sort((a, b) => String(a[ord] ?? "").localeCompare(String(b[ord] ?? ""), "es"));
  }

  function normFilter(E, f) {
    const out = {};
    f = parsePairs(f);
    if (!f || typeof f !== "object") return out;
    for (const [k, v] of Object.entries(f)) {
      if (k === "q") { if (typeof v === "string" && v.trim()) out.q = v.trim().slice(0, 60); continue; }
      const def = E.campos[k];
      if (!def || v === null || v === undefined || v === "") continue;
      if (def.tipo === "enum") { const e = toEnum(def, v); if (e !== undefined) out[k] = e; }
      else if (def.tipo === "booleano") { const b = toBool(v); if (b !== undefined) out[k] = b; }
      else if (["texto", "email"].includes(def.tipo) && typeof v === "string") out[k] = v.trim().slice(0, 60);
    }
    return out;
  }

  function filterLabel(E, f) {
    const p = [];
    for (const [k, v] of Object.entries(f)) {
      if (k === "q") { p.push(`Búsqueda: «${v}»`); continue; }
      const def = E.campos[k];
      if (def.tipo === "booleano") p.push(v ? `Solo ${lower(def.si || def.etiqueta)}s` : `Solo ${lower(def.no || "no " + def.etiqueta)}s`);
      else if (def.tipo === "enum") p.push(`${def.etiqueta}: ${enumLabel(def, v)}`);
      else p.push(`${def.etiqueta}: ${v}`);
    }
    return p.join(" · ");
  }

  function applyFilter(E, rows, f) {
    const textFields = Object.entries(E.campos).filter(([, d]) => ["texto", "email"].includes(d.tipo)).map(([k]) => k);
    return rows.filter(r => Object.entries(f).every(([k, v]) => {
      if (k === "q") return textFields.some(t => lower(r[t]).includes(lower(v)));
      const def = E.campos[k];
      if (def.tipo === "booleano") return !!r[k] === v;
      if (def.tipo === "enum") return r[k] === v;
      return lower(r[k]).includes(lower(v));
    }));
  }

  function stats(E, rows) {
    const out = {};
    const matches = (r, donde) => Object.entries(donde || {}).every(([k, v]) => (E.campos[k]?.tipo === "booleano" ? !!r[k] === v : r[k] === v));
    for (const [name, m] of Object.entries(E.metricas || {})) {
      if (m.tipo === "conteo") out[name] = rows.filter(r => matches(r, m.donde)).length;
      else if (m.tipo === "recientes") {
        const limit = Date.now() - (m.dias || 30) * 864e5;
        out[name] = rows.filter(r => r[m.campo] && new Date(r[m.campo]).getTime() >= limit).length;
      } else if (m.tipo === "reparto") {
        const def = E.campos[m.campo];
        if (def?.tipo === "enum") out[name] = def.valores.map(v => ({ label: v.etiqueta, value: rows.filter(r => r[m.campo] === v.valor).length }));
        else if (def?.tipo === "booleano") out[name] = [{ label: def.si || "Sí", value: rows.filter(r => r[m.campo]).length }, { label: def.no || "No", value: rows.filter(r => !r[m.campo]).length }];
        else {
          const counts = new Map();
          for (const r of rows) { const k = (r[m.campo] ?? "").toString().trim() || "Sin asignar"; counts.set(k, (counts.get(k) || 0) + 1); }
          out[name] = [...counts].map(([label, value]) => ({ label, value })).sort((a, b) => b.value - a.value || a.label.localeCompare(b.label, "es"));
        }
      }
    }
    return out;
  }

  function options(E) {
    const o = {};
    for (const [k, d] of Object.entries(E.campos)) if (d.tipo === "enum") o[k] = d.valores.map(v => ({ value: v.valor, label: v.etiqueta }));
    return o;
  }

  function cleanPrefill(E, p) {
    const out = {};
    p = parsePairs(p);
    if (!p || typeof p !== "object") return out;
    for (const [k, v] of Object.entries(p)) {
      const d = E.campos[k];
      if (!d || d.soloLectura || d.auto) continue;
      if (d.tipo === "enum") { const e = toEnum(d, v); if (e !== undefined) out[k] = e; }
      else if (d.tipo === "booleano") { const b = toBool(v); if (b !== undefined) out[k] = b; }
      else if (["texto", "email"].includes(d.tipo) && typeof v === "string") out[k] = v.slice(0, d.max || 120);
    }
    return out;
  }

  function blank(E, prefill) {
    const r = { id: "" };
    for (const [k, d] of Object.entries(E.campos)) r[k] = d.porDefecto ?? (d.tipo === "booleano" ? false : "");
    return { ...r, ...cleanPrefill(E, prefill) };
  }

  // Contexto que el Renderizador une a la plantilla. Las raíces coinciden con TIPOS[tipo].contexto.
  function context(info, params = {}) {
    const E = info.entity;
    const rows = all(E);
    const f = normFilter(E, params.filter);
    const label = filterLabel(E, f);
    const base = { stats: stats(E, rows), options: options(E), filter: { ...f, active: !!label, label } };
    switch (info.tipo) {
      case "listado": case "libre": {
        const items = applyFilter(E, rows, f);
        return { ...base, items, count: items.length };
      }
      case "alta": return { ...base, item: blank(E, params.prefill) };
      default: {
        const item = rows.find(r => r.id === params.id);
        if (!item) return { missing: true };
        return { ...base, item: info.tipo === "edicion" ? { ...item, ...cleanPrefill(E, params.prefill) } : item };
      }
    }
  }

  function validate(E, values, prev) {
    const errors = {};
    const v = {};
    const rows = all(E);
    for (const [k, d] of Object.entries(E.campos)) {
      if (d.soloLectura || d.auto) continue;
      const raw = values?.[k];
      if (d.tipo === "booleano") { v[k] = raw === true || raw === "true" || raw === "on"; continue; }
      if (d.tipo === "enum") {
        const val = raw === undefined || raw === "" ? d.porDefecto : raw;
        if (!enumValues(d).includes(val)) { if (d.requerido || raw) errors[k] = "Elige una opción."; }
        else v[k] = val;
        continue;
      }
      let s = String(raw ?? "").trim();
      if (d.minusculas) s = s.toLowerCase();
      v[k] = s;
      if (!s) { if (d.requerido) errors[k] = "Este campo es obligatorio."; continue; }
      if (d.min && s.length < d.min) errors[k] = `Necesita al menos ${d.min} caracteres.`;
      else if (d.max && s.length > d.max) errors[k] = `Máximo ${d.max} caracteres.`;
      else if (d.tipo === "email" && !EMAIL_RE.test(s)) errors[k] = "Ese email no tiene un formato válido.";
      else if (d.unico && rows.some(r => lower(r[k]) === lower(s) && r.id !== prev?.id)) errors[k] = `Ya hay otro ${E.etiqueta} con ese ${lower(d.etiqueta)}.`;
    }
    return { v, errors, rows };
  }

  function checkRules(E, op, prev, next, rows) {
    for (const r of E.reglas || []) {
      const res = RULES[r.id]?.({ op, prev, next, all: rows });
      if (res) return res;
    }
    return null;
  }

  function create(E, values) {
    const { v, errors, rows } = validate(E, values, null);
    if (Object.keys(errors).length) return { errors };
    const rec = { id: crypto.randomUUID().slice(0, 8), ...v };
    for (const [k, d] of Object.entries(E.campos)) if (d.auto === "alCrear" && d.tipo === "fecha") rec[k] = new Date().toISOString().slice(0, 10);
    const rule = checkRules(E, "alta", null, rec, rows);
    if (rule) return { errors: { [rule.campo || "_"]: rule.mensaje } };
    store.insert(E.nombreInterno, rec);
    return { record: rec };
  }

  function update(E, id, values) {
    const prev = store.get(E.nombreInterno, id);
    if (!prev) return { notFound: true };
    const { v, errors, rows } = validate(E, values, prev);
    if (Object.keys(errors).length) return { errors };
    const next = { ...prev, ...v };
    const rule = checkRules(E, "edicion", prev, next, rows);
    if (rule) return { errors: { [rule.campo || "_"]: rule.mensaje } };
    store.update(E.nombreInterno, next);
    return { record: next };
  }

  function remove(E, id) {
    const prev = store.get(E.nombreInterno, id);
    if (!prev) return { notFound: true };
    const rule = checkRules(E, "baja", prev, null, all(E));
    if (rule) return { errors: { _: rule.mensaje } };
    store.remove(E.nombreInterno, id);
    return { record: prev };
  }

  return { all, normFilter, cleanPrefill, context, create, update, remove };
}
