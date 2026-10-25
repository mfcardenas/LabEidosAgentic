// Guardián — determinista. Revisa la plantilla que propone el Compositor contra el catálogo
// y la spec, y corrige lo que puede. Solo rechaza (y pide corrección) si no hay raíz Screen.

export const CATALOG = {
  Screen: { props: ["title", "subtitle", "actions"], container: true },
  Section: { props: ["title"], container: true },
  Row: { props: [], container: true },
  Text: { props: ["value", "variant"] },
  Stat: { props: ["label", "value", "hint", "tone"] },
  Table: { props: ["rows", "columns", "rowAction", "empty"] },
  KeyValue: { props: ["items"] },
  Badge: { props: ["value", "tone"] },
  BarList: { props: ["title", "items"] },
  Form: { props: ["fields", "submit", "cancel"] },
  Button: { props: ["label", "variant", "action"] },
  Alert: { props: ["tone", "title", "text"] },
  Empty: { props: ["title", "text", "button"] }
};
const MAX_NODES = 60;
const FORMATS = ["text", "person", "badge", "status", "date", "email"];

export class GuardError extends Error {}

// gpt-oss a veces copia del catálogo {"$bind":"…"} como cadena en vez de como objeto.
function parseBind(v) {
  if (typeof v !== "string" || !/^\s*\{\s*"\$bind"/.test(v)) return v;
  try { const o = JSON.parse(v); return typeof o?.$bind === "string" ? { $bind: o.$bind } : v; } catch { return v; }
}

/**
 * @param tpl   lo que devolvió el Compositor
 * @param info  intentInfo(specs, intent)
 * @param specs specs completas
 * @returns {tpl, fixes[], warnings[], nodes}
 */
export function guard(tpl, info, specs) {
  const fixes = [], warnings = [];
  if (!tpl || typeof tpl !== "object" || Array.isArray(tpl)) throw new GuardError("La respuesta no es un objeto JSON.");
  if (tpl.type !== "Screen" && tpl.root?.type === "Screen") tpl = tpl.root;
  if (tpl.type !== "Screen") throw new GuardError("La raíz debe ser un componente Screen.");

  const E = info.entity;
  const tipo = info.tipo;
  const intents = specs.app.intents;
  const roots = new Set([...info.tipoInfo.contexto]);
  const bajaIntent = Object.entries(intents).find(([, it]) => it.entidad === info.entidad && it.tipo === "baja")?.[0];
  let count = 0, forms = 0;
  const buttons = [];

  function checkBindings(value, where, extra = []) {
    const s = JSON.stringify(value ?? "");
    const refs = [...s.matchAll(/\{\{\s*([\w]+)[\w.]*\s*\}\}/g)].map(m => m[1]);
    const binds = [...s.matchAll(/\\?"\$bind\\?"\s*:\s*\\?"([\w]+)/g)].map(m => m[1]);
    for (const r of [...refs, ...binds]) if (!roots.has(r) && !extra.includes(r)) warnings.push(`${where}: enlaza «${r}», que no existe en este contexto (se verá vacío)`);
    for (const m of s.matchAll(/\{\{([^}]*)\}\}/g)) if (!/^\s*[\w.]+\s*$/.test(m[1])) warnings.push(`${where}: «{{${m[1]}}}» no es un enlace válido (solo rutas con puntos), se verá tal cual`);
  }

  function act(a, where, extraRoots = []) {
    if (!a || typeof a !== "object") { fixes.push(`${where}: sin acción, se quita`); return null; }
    checkBindings(a, where, extraRoots);
    if (a.type === "navigate") {
      if (!intents[a.intent]) { fixes.push(`${where}: el intent «${a.intent}» no está en la spec, se quita`); return null; }
      return { type: "navigate", intent: a.intent, params: a.params && typeof a.params === "object" ? a.params : {} };
    }
    if (a.type === "delete") {
      if (tipo !== "baja") {
        if (!bajaIntent) { fixes.push(`${where}: borrado sin pantalla de confirmación posible, se quita`); return null; }
        fixes.push(`${where}: borrado fuera de la confirmación → ahora lleva a confirmar`);
        return { type: "navigate", intent: bajaIntent, params: { id: a.id || "{{item.id}}" } };
      }
      return { type: "delete", id: a.id || "{{item.id}}" };
    }
    if (a.type === "ask" && typeof a.text === "string" && a.text.trim()) return { type: "ask", text: a.text.slice(0, 200) };
    fixes.push(`${where}: la acción «${a.type}» no existe, se quita`);
    return null;
  }

  function form(n, out, where) {
    if (!["alta", "edicion"].includes(tipo)) { fixes.push(`${where}: formulario fuera de alta/edición, se quita`); return null; }
    forms++;
    const C = E.campos;
    const seen = new Set();
    const fields = [];
    for (const f of Array.isArray(n.fields) ? n.fields : []) {
      const name = typeof f === "string" ? f : f?.field;
      if (!C[name]) { fixes.push(`${where}: el campo «${name}» no existe en la entidad, se quita`); continue; }
      if (C[name].soloLectura || C[name].auto) { fixes.push(`${where}: «${name}» lo rellena el sistema, se quita del formulario`); continue; }
      if (seen.has(name)) continue;
      seen.add(name);
      fields.push({ field: name, label: (typeof f?.label === "string" && f.label) || C[name].etiqueta, ...(typeof f?.help === "string" ? { help: f.help } : {}) });
    }
    for (const [name, def] of Object.entries(C)) {
      if (def.requerido && !def.soloLectura && !def.auto && !seen.has(name)) {
        fields.push({ field: name, label: def.etiqueta });
        seen.add(name);
        fixes.push(`${where}: faltaba el campo obligatorio «${name}», se añade`);
      }
    }
    out.fields = fields;
    out.submit = { label: (typeof n.submit?.label === "string" && n.submit.label) || (tipo === "alta" ? `Crear ${E.etiqueta}` : "Guardar cambios") };
    if (n.cancel && typeof n.cancel === "object") {
      const a = act(n.cancel.action, `${where}.cancel`);
      if (a) out.cancel = { label: n.cancel.label || "Cancelar", action: a };
    }
    return out;
  }

  function node(n, where) {
    if (!n || typeof n !== "object") return null;
    if (n.props && typeof n.props === "object" && !Array.isArray(n.props)) {
      const { props, ...rest } = n;
      n = { ...props, ...rest };
      fixes.push(`${where}: las propiedades venían dentro de «props», se aplanan`);
    }
    const def = CATALOG[n.type];
    if (!def) { fixes.push(`${where}: el componente «${n.type}» no está en el catálogo, se quita`); return null; }
    if (++count > MAX_NODES) { if (count === MAX_NODES + 1) fixes.push(`más de ${MAX_NODES} nodos, se recorta`); return null; }
    const out = { type: n.type };
    if (typeof n.when === "string") { out.when = n.when; checkBindings(`{{${n.when.replace(/^!/, "")}}}`, `${n.type}.when`); }
    const allowed = new Set(["type", "when", "children", ...def.props]);
    const extra = Object.keys(n).filter(k => !allowed.has(k));
    if (extra.length) fixes.push(`${where}: propiedades no permitidas (${extra.join(", ")}), se quitan`);
    for (const k of def.props) if (n[k] !== undefined) {
      out[k] = parseBind(n[k]);
      if (out[k] !== n[k]) fixes.push(`${where}.${k}: el $bind venía como texto, se convierte en enlace`);
    }

    if (def.container) out.children = (Array.isArray(n.children) ? n.children : []).map((c, i) => node(c, `${n.type}[${i}]`)).filter(Boolean);
    if (n.type === "Screen") {
      if (typeof out.title !== "string" || !out.title.trim()) { out.title = info.descripcion.split(/[.,:]/)[0]; fixes.push("Screen: sin título, se usa el del intent"); }
      out.actions = (Array.isArray(n.actions) ? n.actions : []).map((b, i) => {
        if (!b || typeof b !== "object") return null;
        if (b.type && b.type !== "Button") { fixes.push(`Screen.actions[${i}]: «${b.type}» no es un botón, se quita`); return null; }
        if (!b.type) fixes.push(`Screen.actions[${i}]: faltaba type "Button", se añade`);
        return node({ ...b, type: "Button" }, "Screen.actions");
      }).filter(Boolean);
    }
    for (const k of ["title", "subtitle", "value", "label", "hint", "text"]) if (out[k] !== undefined && n.type !== "Button") checkBindings(out[k], `${n.type}.${k}`);

    if (n.type === "Button") {
      if (typeof out.label !== "string" || !out.label.trim()) { fixes.push(`${where}: botón sin texto, se quita`); return null; }
      if (!["primary", "secondary", "danger", "ghost"].includes(out.variant)) out.variant = "secondary";
      out.action = act(n.action, `Botón «${out.label}»`);
      if (!out.action) return null;
      if (out.action.type === "delete") out.variant = "danger";
      else if (out.variant === "danger") out.variant = "secondary";
      buttons.push(out);
    }
    if (n.type === "Empty") out.button = n.button?.type === "Button" ? node(n.button, "Empty.button") : undefined;
    if (n.type === "Table") {
      if (!Array.isArray(n.columns) || !n.columns.length) { fixes.push(`${where}: tabla sin columnas, se quita`); return null; }
      out.columns = n.columns.filter(c => c && typeof c.field === "string").map(c => {
        if (!E.campos[c.field] && c.field !== "id") warnings.push(`Tabla: la columna «${c.field}» no es un campo de ${info.entidad}`);
        return { field: c.field, label: String(c.label || E.campos[c.field]?.etiqueta || c.field), format: FORMATS.includes(c.format) ? c.format : "text" };
      });
      if (!out.rows) out.rows = { $bind: "items" };
      checkBindings(out.rows, "Table.rows");
      if (n.rowAction) out.rowAction = act(n.rowAction, "Fila de tabla", ["row"]) || undefined;
    }
    if (n.type === "KeyValue") {
      out.items = (Array.isArray(n.items) ? n.items : []).filter(i => i && i.label !== undefined).map(i => ({ label: i.label, value: i.value, ...(FORMATS.includes(i.format) ? { format: i.format } : {}) }));
      checkBindings(out.items, "KeyValue");
    }
    if (n.type === "BarList") checkBindings(out.items, "BarList.items");
    if (n.type === "Form") return form(n, out, where);
    return out;
  }

  const root = node(tpl, "Screen");
  const primaries = buttons.filter(b => b.variant === "primary");
  primaries.slice(forms ? 0 : 1).forEach(b => { b.variant = "secondary"; fixes.push(`«${b.label}»: sobraba un botón primario, pasa a secundario`); });
  if (tipo === "baja" && !buttons.some(b => b.action.type === "delete")) {
    root.actions.push({ type: "Button", label: "Dar de baja", variant: "danger", action: { type: "delete", id: "{{item.id}}" } });
    fixes.push("faltaba el botón de confirmar la baja, se añade");
  }
  if (["alta", "edicion"].includes(tipo) && !forms) throw new GuardError("Una pantalla de alta o edición necesita un componente Form.");
  return { tpl: root, fixes, warnings: [...new Set(warnings)], nodes: count };
}
