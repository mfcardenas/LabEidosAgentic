// Cliente del modelo local. Habla con Ollama (API nativa) o con cualquier servidor
// compatible con OpenAI (LM Studio, llama.cpp, vLLM). Pensado para gpt-oss.
import fs from "node:fs";
import path from "node:path";
import { config } from "./config.js";

export class LLMError extends Error {
  constructor(code, message, raw) { super(message); this.code = code; this.raw = raw; }
}

const L = config.llm;
const AZ = config.azure;
let logSeq = 0;

// Perfiles de modelo seleccionables desde /admin.html. Las claves nunca salen del servidor.
const PROFILES = {
  local: {
    id: "local", label: L.provider === "ollama" ? "Local · Ollama" : "Local · servidor compatible con OpenAI",
    provider: L.provider, baseUrl: L.baseUrl, apiKey: L.apiKey,
    routerModel: L.routerModel, composerModel: L.composerModel,
    routerReasoning: L.routerReasoning, composerReasoning: L.composerReasoning, jsonMode: L.jsonMode, configured: true
  },
  azure: {
    id: "azure", label: "Cloud · Azure OpenAI",
    provider: "azure", baseUrl: AZ.endpoint, apiKey: AZ.apiKey, apiVersion: AZ.apiVersion,
    routerModel: AZ.deployment, composerModel: AZ.deployment,
    routerReasoning: "", composerReasoning: "", jsonMode: true,
    configured: Boolean(AZ.endpoint && AZ.apiKey && AZ.deployment)
  }
};
let activeId = PROFILES[config.llmProfile]?.configured ? config.llmProfile : "local";

export const activeProfile = () => PROFILES[activeId];
export function setActiveProfile(id) {
  if (!PROFILES[id]) throw new LLMError("bad_profile", `No existe el perfil «${id}».`);
  if (!PROFILES[id].configured) throw new LLMError("not_configured", `${PROFILES[id].label} no está configurado en .env.`);
  activeId = id;
  return PROFILES[id];
}
export function listProfiles() {
  return Object.values(PROFILES).map(({ apiKey, ...p }) => ({ ...p, active: p.id === activeId }));
}
export const getProfile = id => PROFILES[id];

function logExchange(label, model, prompt, reply) {
  if (!L.logPrompts) return;
  try {
    fs.mkdirSync(config.logsDir, { recursive: true });
    const name = `${new Date().toISOString().replace(/[:.]/g, "-")}-${++logSeq}-${label}.txt`;
    fs.writeFileSync(path.join(config.logsDir, name), `MODELO: ${model}\n\n=== PROMPT ===\n${prompt}\n\n=== RESPUESTA ===\n${reply}\n`);
  } catch { /* el log nunca debe romper la petición */ }
}

/** Una llamada de chat. Devuelve {text, thinking, seconds}. */
export async function chat({ model, reasoning, prompt, signal, label = "llm", profile = activeProfile(), json = profile.jsonMode }) {
  const P = profile;
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(new LLMError("timeout", "timeout")), L.timeoutMs);
  const onAbort = () => ctl.abort(new LLMError("cancelled", "cancelled"));
  if (signal) { if (signal.aborted) onAbort(); else signal.addEventListener("abort", onAbort, { once: true }); }
  const t0 = Date.now();
  const messages = [{ role: "user", content: prompt }];
  const headers = { "Content-Type": "application/json" };
  let url, body;
  if (P.provider === "ollama") {
    url = `${P.baseUrl}/api/chat`;
    body = { model, messages, stream: false, options: { num_ctx: L.numCtx } };
    if (L.temperature !== null) body.options.temperature = L.temperature;
    if (reasoning) body.think = reasoning;            // gpt-oss acepta "low" | "medium" | "high"
    if (json) body.format = "json";
  } else if (P.provider === "azure") {
    url = `${P.baseUrl}/openai/deployments/${encodeURIComponent(model)}/chat/completions?api-version=${encodeURIComponent(P.apiVersion)}`;
    body = { messages };
    if (L.temperature !== null) body.temperature = L.temperature;
    if (json) body.response_format = { type: "json_object" };
    headers["api-key"] = P.apiKey;
  } else {
    url = `${P.baseUrl}/chat/completions`;
    body = { model, messages };
    if (L.temperature !== null) body.temperature = L.temperature;
    if (reasoning) body.reasoning_effort = reasoning;
    if (json) body.response_format = { type: "json_object" };
    if (P.apiKey) headers.Authorization = `Bearer ${P.apiKey}`;
  }
  const serverName = P.provider === "ollama" ? "Ollama" : P.provider === "azure" ? "Azure OpenAI" : "el servidor del modelo";

  let res;
  try {
    res = await fetch(url, { method: "POST", headers, body: JSON.stringify(body), signal: ctl.signal });
  } catch (e) {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
    const reason = ctl.signal.reason;
    if (reason instanceof LLMError) {
      if (reason.code === "timeout") throw new LLMError("timeout", `El modelo ${model} no respondió en ${Math.round(L.timeoutMs / 1000)} s. Sube LLM_TIMEOUT_MS o usa un esfuerzo de razonamiento menor.`);
      throw reason;
    }
    throw new LLMError("unreachable", `No puedo conectar con ${P.baseUrl}. ¿Está ${serverName} disponible?`);
  }
  let payload, rawText = "";
  try {
    rawText = await res.text();
    payload = JSON.parse(rawText);
  } catch (e) {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onAbort);
    const reason = ctl.signal.reason;
    if (reason instanceof LLMError) throw reason.code === "timeout" ? new LLMError("timeout", `El modelo ${model} no respondió a tiempo.`) : reason;
    throw new LLMError("bad_response", `Respuesta ilegible del servidor del modelo (HTTP ${res.status}).`, rawText.slice(0, 500));
  }
  clearTimeout(timer);
  signal?.removeEventListener("abort", onAbort);

  if (!res.ok) {
    const msg = payload?.error?.message || payload?.error || rawText.slice(0, 300);
    if (P.provider === "azure" && (res.status === 401 || res.status === 403))
      throw new LLMError("auth", "Azure OpenAI rechazó la API key. Revisa AZURE_OPENAI_API_KEY en .env.");
    if (P.provider === "azure" && res.status === 404)
      throw new LLMError("model_missing", `Azure OpenAI no encuentra el deployment «${model}». Revisa AZURE_OPENAI_CHAT_DEPLOYMENT y AZURE_OPENAI_ENDPOINT.`);
    if (res.status === 404 || /not found|no such model|pull/i.test(String(msg)))
      throw new LLMError("model_missing", P.provider === "ollama"
        ? `Falta el modelo ${model}. Descárgalo con: ollama pull ${model}`
        : `El servidor no tiene cargado el modelo ${model}.`);
    throw new LLMError("upstream", `El servidor del modelo devolvió un error (HTTP ${res.status}): ${msg}`);
  }

  let text, thinking = "";
  if (P.provider === "ollama") { text = payload?.message?.content ?? ""; thinking = payload?.message?.thinking ?? ""; }
  else { const m = payload?.choices?.[0]?.message || {}; text = m.content ?? ""; thinking = m.reasoning_content ?? m.reasoning ?? ""; }
  text = String(text).replace(/<think>[\s\S]*?<\/think>/g, "").trim();
  logExchange(label, model, prompt, (thinking ? `[razonamiento]\n${thinking}\n\n[respuesta]\n` : "") + text);
  if (!text) throw new LLMError("empty", `El modelo ${model} no devolvió texto. Si usa razonamiento, prueba con más contexto (LLM_NUM_CTX) o menos esfuerzo.`);
  return { text, thinking, seconds: (Date.now() - t0) / 1000 };
}

/** Saca un valor JSON de una respuesta: entera, en un bloque ```json``` o del primer { al último }. */
export function extractJSON(text) {
  const tryParse = s => { try { return JSON.parse(s); } catch { return undefined; } };
  let v = tryParse(text);
  if (v !== undefined) return v;
  const fence = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  if (fence) { v = tryParse(fence[1].trim()); if (v !== undefined) return v; }
  const a = text.indexOf("{"), b = text.lastIndexOf("}");
  if (a >= 0 && b > a) { v = tryParse(text.slice(a, b + 1)); if (v !== undefined) return v; }
  throw new LLMError("invalid_json", "La respuesta del modelo no es un JSON válido.", text.slice(0, 2000));
}

export async function chatJSON(opts) {
  const r = await chat(opts);
  return { value: extractJSON(r.text), seconds: r.seconds };
}

/** Comprueba que el servidor responde y que los modelos están disponibles. */
export async function health(P = activeProfile()) {
  const out = { profile: P.id, label: P.label, provider: P.provider, baseUrl: P.baseUrl, routerModel: P.routerModel, composerModel: P.composerModel, reachable: false, missing: [] };
  // Azure no tiene un listado barato de deployments con api-key: basta con que esté configurado; /admin.html permite probarlo.
  if (P.provider === "azure") { out.reachable = P.configured; return out; }
  try {
    const ctl = AbortSignal.timeout(4000);
    const headers = P.apiKey ? { Authorization: `Bearer ${P.apiKey}` } : {};
    if (P.provider === "ollama") {
      const r = await fetch(`${P.baseUrl}/api/tags`, { signal: ctl });
      const j = await r.json();
      out.reachable = true;
      const names = (j.models || []).flatMap(m => [m.name, m.model]).filter(Boolean);
      const has = m => names.some(n => n === m || n === `${m}:latest` || n.replace(/:latest$/, "") === m);
      out.missing = [...new Set([P.routerModel, P.composerModel])].filter(m => !has(m));
    } else {
      const r = await fetch(`${P.baseUrl}/models`, { signal: ctl, headers });
      const j = await r.json();
      out.reachable = true;
      const ids = (j.data || []).map(m => m.id);
      if (ids.length) out.missing = [...new Set([P.routerModel, P.composerModel])].filter(m => !ids.includes(m));
    }
  } catch { out.reachable = false; }
  return out;
}
