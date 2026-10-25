// Arranca Eidos con el modelo SIMULADO, sin necesidad de Ollama ni gpt-oss.
// Sirve para ver el flujo completo; las pantallas son fijas. Usa una BD aparte (data/demo.db).
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const MOCK_PORT = process.env.MOCK_PORT || "11435";
const env = { ...process.env, MOCK_PORT, LLM_PROVIDER: "ollama", LLM_BASE_URL: `http://127.0.0.1:${MOCK_PORT}`, ROUTER_MODEL: "gpt-oss:20b", COMPOSER_MODEL: "gpt-oss:20b", DB_FILE: "data/demo.db" };

const mock = spawn(process.execPath, [path.join(root, "scripts/mock-llm.js")], { env, stdio: "inherit" });
setTimeout(() => {
  const server = spawn(process.execPath, ["--disable-warning=ExperimentalWarning", path.join(root, "server/index.js")], { env, stdio: "inherit" });
  const stop = () => { server.kill(); mock.kill(); process.exit(0); };
  process.on("SIGINT", stop); process.on("SIGTERM", stop);
  server.on("exit", code => { mock.kill(); process.exit(code ?? 0); });
}, 300);
console.log("[demo] Modo demostración: el modelo es simulado y las pantallas son fijas. Para usar gpt-oss: npm start");
