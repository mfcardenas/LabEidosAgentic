// Motor de enlaces: resuelve valores literales, rutas JSON Pointer y plantillas contra el modelo de datos.
// Nunca evalúa código.
import type { Condition, Value } from "./types";

export type Data = Record<string, unknown>;

export function get(data: Data, pointer: string): unknown {
  return pointer.split("/").slice(1).reduce<unknown>((acc, key) => (acc == null ? undefined : (acc as Record<string, unknown>)[key]), data);
}

export function resolve(value: unknown, data: Data): unknown {
  if (value && typeof value === "object") {
    const v = value as Record<string, unknown>;
    if (typeof v.path === "string") return get(data, v.path);
    if (typeof v.template === "string") return v.template.replace(/\$\{(\/[A-Za-z0-9_/]+)\}/g, (_, p: string) => text(get(data, p)));
  }
  return value;
}

export function resolveAll(obj: Record<string, Value> | undefined, data: Data): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(obj ?? {})) out[k] = resolve(v, data);
  return out;
}

export function truthy(v: unknown): boolean {
  return Array.isArray(v) ? v.length > 0 : Boolean(v);
}

export function visible(cond: Condition | undefined, data: Data): boolean {
  if (!cond) return true;
  if ("not" in cond) return !truthy(get(data, cond.not.path));
  return truthy(get(data, cond.path));
}

export function text(v: unknown): string {
  if (v === true) return "Sí";
  if (v === false) return "No";
  if (v == null) return "";
  if (Array.isArray(v)) return String(v.length);
  return typeof v === "object" ? "" : String(v);
}

/** Campo de la entidad al que apunta un valor enlazado (/item/rol → rol; /row/sala_titulo → sala). */
export function fieldOf(value: unknown): string | null {
  if (value && typeof value === "object" && typeof (value as { path?: unknown }).path === "string") {
    const last = (value as { path: string }).path.split("/").pop() ?? "";
    return last.replace(/_titulo$/, "");
  }
  return null;
}
