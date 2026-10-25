// Registro del catálogo: componente → implementación. Es la única UI que existe; no conoce ningún dominio.
// Cada componente del catálogo (platform/src/eidos/catalog) debe tener aquí su implementación (F8).
import { fieldOf, resolve, resolveAll, text, visible, type Data } from "./binding";
import type { Action, CommandResult, Component, EntitySpec, FieldSpec, Format, Value } from "./types";

export interface Host {
  navigate(view: string, params: Record<string, unknown>): void;
  command(command: string, input: Record<string, unknown>): Promise<CommandResult>;
}

export interface Ctx {
  byId: Map<string, Component>;
  data: Data;
  entity: EntitySpec;
  host: Host;
  notify(message: string): void;
}

type Render = (c: Component, ctx: Ctx) => HTMLElement;

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, unknown> | null = null, ...kids: unknown[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs ?? {})) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = String(v);
    else if (k === "text") el.textContent = String(v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v as EventListener);
    else el.setAttribute(k, v === true ? "" : String(v));
  }
  for (const kid of kids.flat(Infinity)) if (kid != null && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
  return el;
}

const str = (v: unknown, ctx: Ctx) => text(resolve(v, ctx.data));

function badge(label: string, tone = "") {
  return h("span", { class: `g-badge ${tone}`, text: label });
}

function fmtDate(v: unknown, withTime: boolean) {
  const d = new Date(String(v));
  if (!v || isNaN(d.getTime())) return text(v);
  return d.toLocaleString("es-ES", withTime ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric" });
}

export function formatValue(value: unknown, format: Format | undefined, field: FieldSpec | undefined): Node {
  let fmt = format;
  if (!fmt || fmt === "text") {
    fmt = field?.tipo === "enum" ? "badge" : field?.tipo === "booleano" ? "status" : field?.tipo === "fecha" ? "date" : field?.tipo === "fechahora" ? "datetime" : "text";
  }
  switch (fmt) {
    case "badge": {
      const opt = field?.valores.find((x) => x.valor === value);
      return badge(opt ? opt.etiqueta : text(value), opt?.tono);
    }
    case "status": return value ? badge(field?.si ?? "Sí", "good") : badge(field?.no ?? "No");
    case "date": return document.createTextNode(fmtDate(value, false));
    case "datetime": return document.createTextNode(fmtDate(value, true));
    case "email": return h("span", { class: "mono", text: text(value) });
    case "number": return document.createTextNode(typeof value === "number" ? value.toLocaleString("es-ES") : text(value));
    case "person": {
      const name = text(value);
      const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((w) => w[0]!.toUpperCase()).join("");
      const hue = [...name].reduce((a, ch) => a + ch.charCodeAt(0), 0) % 5;
      return h("span", { class: "g-person" }, h("span", { class: `av c${hue}`, "aria-hidden": "true", text: initials }), h("span", { text: name }));
    }
    default: return document.createTextNode(text(value));
  }
}

async function perform(action: Action | undefined, ctx: Ctx, scope: Data = ctx.data) {
  if (!action) return;
  if ("function" in action) {
    ctx.host.navigate(action.args.view, resolveAll(action.args.params, scope));
    return;
  }
  const result = await ctx.host.command(action.command, resolveAll(action.input as Record<string, Value>, scope));
  if (!result.ok) ctx.notify(Object.values(result.errors ?? {}).join(" ") || "No se ha podido completar.");
  else if (result.next) ctx.host.navigate(result.next.view, result.next.params);
}

export function render(id: string, ctx: Ctx): HTMLElement | null {
  const c = ctx.byId.get(id);
  if (!c || !visible(c.visible, ctx.data)) return null;
  const impl = components[c.component];
  return impl ? impl(c, ctx) : null;
}

const kids = (c: Component, ctx: Ctx) => (c.children ?? []).map((k) => render(k, ctx));

export const components: Record<string, Render> = {
  Page: (c, ctx) =>
    h("div", { class: "g-screen" },
      h("div", { class: "g-head" },
        h("div", null, h("h2", { text: str(c.title, ctx) }), c.subtitle != null ? h("p", { class: "sub", text: str(c.subtitle, ctx) }) : null),
        (c.actions ?? []).length ? h("div", { class: "g-actions" }, (c.actions ?? []).map((a) => render(a, ctx))) : null),
      h("div", { class: "g-body" }, kids(c, ctx))),

  Card: (c, ctx) => h("section", { class: "g-section" }, c.title != null ? h("h3", { text: str(c.title, ctx) }) : null, kids(c, ctx)),

  Columns: (c, ctx) => h("div", { class: "g-row" }, kids(c, ctx)),

  Stat: (c, ctx) =>
    h("div", { class: `g-stat ${c.tone ?? ""}` },
      h("span", { class: "l", text: String(c.label) }), h("span", { class: "v", text: str(c.value, ctx) }),
      c.hint ? h("span", { class: "hnt", text: String(c.hint) }) : null),

  Table: (c, ctx) => {
    const rows = resolve(c.rows, ctx.data);
    const list = Array.isArray(rows) ? (rows as Data[]) : [];
    const columns = c.columns as { field: string; label: string; format?: Format }[];
    if (!list.length) return h("p", { class: "g-text muted", text: String(c.empty ?? "No hay nada que mostrar.") });
    return h("div", { class: "g-table-wrap" }, h("table", { class: "g-table" },
      h("thead", null, h("tr", null, columns.map((col) => h("th", { text: col.label })))),
      h("tbody", null, list.map((row) => {
        const scope = { ...ctx.data, row };
        const tr = h("tr", c.rowAction ? { class: "click", tabindex: "0", role: "button" } : null,
          columns.map((col) => h("td", { "data-label": col.label, class: col.format === "email" ? "email" : null },
            h("span", { class: "cell" }, formatValue(row[col.field], col.format, ctx.entity.campos[col.field.replace(/_titulo$/, "")])))));
        if (c.rowAction) {
          const go = () => perform(c.rowAction as Action, ctx, scope);
          tr.addEventListener("click", go);
          tr.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); } });
        }
        return tr;
      }))));
  },

  KeyValue: (c, ctx) =>
    h("dl", { class: "g-kv" }, (c.items as { label: string; value: Value; format?: Format }[]).map((it) => {
      const field = fieldOf(it.value);
      return [h("dt", { text: it.label }), h("dd", null, formatValue(resolve(it.value, ctx.data), it.format, field ? ctx.entity.campos[field] : undefined))];
    })),

  Form: (c, ctx) => {
    const item = (ctx.data.item ?? {}) as Data;
    const options = (ctx.data.options ?? {}) as Record<string, { value: string; label: string }[]>;
    const errEls: Record<string, HTMLElement> = {};
    const form = h("form", { class: "g-form", novalidate: true });
    for (const f of c.fields as { field: string; label?: string; help?: string }[]) {
      const def = ctx.entity.campos[f.field];
      if (!def) continue;
      const id = `f-${f.field}`;
      const label = f.label ?? def.etiqueta;
      const v = item[f.field];
      let input: HTMLElement;
      if (def.tipo === "enum" || def.tipo === "referencia") {
        input = h("select", { id, name: f.field },
          def.requerido ? null : h("option", { value: "" }, "—"),
          (options[f.field] ?? []).map((o) => h("option", { value: o.value, selected: o.value === v }, o.label)));
      } else if (def.tipo === "booleano") {
        input = h("input", { id, name: f.field, type: "checkbox", checked: Boolean(v) });
      } else {
        const type = { email: "email", numero: "number", fecha: "date", fechahora: "datetime-local" }[def.tipo as string] ?? "text";
        input = h("input", { id, name: f.field, type, value: v == null ? "" : String(v).slice(0, def.tipo === "fechahora" ? 16 : undefined), autocomplete: "off" });
      }
      errEls[f.field] = h("span", { class: "err", role: "alert" });
      form.append(def.tipo === "booleano"
        ? h("div", { class: "g-field" }, h("label", { class: "g-switch", for: id }, input, label), f.help ? h("span", { class: "help", text: f.help }) : null, errEls[f.field])
        : h("div", { class: "g-field" }, h("label", { for: id, text: label + (def.requerido ? " *" : "") }), input, f.help ? h("span", { class: "help", text: f.help }) : null, errEls[f.field]));
    }
    const general = h("div", { class: "g-alert danger", role: "alert", hidden: true });
    const submit = h("button", { class: "g-btn primary", type: "submit" }, String((c.submit as { label: string }).label));
    const cancel = c.cancel as { label: string; action: Action } | undefined;
    form.append(general, h("div", { class: "btns" }, submit,
      cancel ? h("button", { class: "g-btn ghost", type: "button", onclick: () => perform(cancel.action, ctx) }, cancel.label) : null));
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const values: Record<string, unknown> = item.id ? { id: item.id } : {};
      for (const el of Array.from(form.elements) as HTMLInputElement[]) if (el.name) values[el.name] = el.type === "checkbox" ? el.checked : el.value;
      submit.disabled = true;
      const result = await ctx.host.command(String(c.command), values);
      submit.disabled = false;
      for (const [k, el] of Object.entries(errEls)) el.textContent = result.errors?.[k] ?? "";
      const other = Object.entries(result.errors ?? {}).filter(([k]) => !errEls[k]).map(([, v]) => v);
      general.hidden = !other.length;
      general.textContent = other.join(" ");
      if (result.ok && result.next) ctx.host.navigate(result.next.view, result.next.params);
    });
    return form;
  },

  Button: (c, ctx) => h("button", { class: `g-btn ${c.variant ?? "secondary"}`, type: "button", onclick: () => perform(c.action as Action, ctx) }, String(c.label)),

  Alert: (c, ctx) => h("div", { class: `g-alert ${c.tone ?? "info"}`, role: "status" }, c.title ? h("b", { text: String(c.title) }) : null, str(c.text, ctx)),

  Empty: (c, ctx) =>
    h("div", { class: "g-empty" }, h("b", { text: String(c.title) }), h("p", { text: String(c.text) }),
      (c.actions ?? []).length ? h("div", { class: "g-actions" }, (c.actions ?? []).map((a) => render(a, ctx))) : null),

  Text: (c, ctx) => h("p", { class: `g-text ${c.variant ?? "body"}`, text: str(c.value, ctx) }),

  BarList: (c, ctx) => {
    const items = ((resolve(c.items, ctx.data) as { label: string; value: number }[]) ?? []).filter((x) => x && typeof x === "object");
    const max = Math.max(1, ...items.map((x) => Number(x.value) || 0));
    return h("div", { class: "g-bars" }, items.map((x) => h("div", { class: "b" },
      h("span", { text: x.label }),
      h("div", { class: "track" }, h("div", { class: "fill", style: `width:${((Number(x.value) || 0) / max) * 100}%` })),
      h("span", { class: "n", text: String(x.value) }))));
  },
};
