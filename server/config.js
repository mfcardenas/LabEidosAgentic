// Configuración: lee .env (si existe) sin dependencias y aplica valores por defecto.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

function loadDotEnv(file) {
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const i = line.indexOf("=");
    if (i < 0) continue;
    const key = line.slice(0, i).trim();
    let val = line.slice(i + 1).trim();
    if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) val = val.slice(1, -1);
    if (process.env[key] === undefined) process.env[key] = val;
  }
}
loadDotEnv(path.join(ROOT, ".env"));

const env = (k, d) => (process.env[k] === undefined || process.env[k] === "" ? d : process.env[k]);
const bool = (k, d) => { const v = env(k, null); return v === null ? d : /^(1|true|yes|si|sí)$/i.test(v); };
const num = (k, d) => { const v = Number(env(k, NaN)); return Number.isFinite(v) ? v : d; };

const provider = env("LLM_PROVIDER", "ollama").toLowerCase();

export const config = {
  port: num("PORT", 3000),
  host: env("HOST", "127.0.0.1"),
  llm: {
    provider: provider === "openai" ? "openai" : "ollama",
    baseUrl: env("LLM_BASE_URL", provider === "openai" ? "http://localhost:1234/v1" : "http://localhost:11434").replace(/\/+$/, ""),
    apiKey: env("LLM_API_KEY", ""),
    routerModel: env("ROUTER_MODEL", "gpt-oss:20b"),
    composerModel: env("COMPOSER_MODEL", "gpt-oss:20b"),
    routerReasoning: env("ROUTER_REASONING", "low"),
    composerReasoning: env("COMPOSER_REASONING", "medium"),
    numCtx: num("LLM_NUM_CTX", 16384),
    temperature: env("LLM_TEMPERATURE", "") === "" ? null : num("LLM_TEMPERATURE", null),
    jsonMode: bool("LLM_JSON_MODE", false),
    timeoutMs: num("LLM_TIMEOUT_MS", 600000),
    logPrompts: bool("LOG_PROMPTS", false)
  },
  llmProfile: env("LLM_PROFILE", "local").toLowerCase() === "azure" ? "azure" : "local",
  azure: {
    endpoint: env("AZURE_OPENAI_ENDPOINT", "").replace(/\/+$/, ""),
    apiKey: env("AZURE_OPENAI_API_KEY", ""),
    apiVersion: env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
    deployment: env("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
  },
  dbFile: path.resolve(ROOT, env("DB_FILE", "data/eidos.db")),
  seed: bool("SEED", true),
  specsDir: path.join(ROOT, "specs"),
  seedsDir: path.join(ROOT, "seeds"),
  publicDir: path.join(ROOT, "public"),
  logsDir: path.join(ROOT, "data", "logs")
};
