// Comprueba que el modelo responde y devuelve JSON. Uso: npm run check-llm [-- local|azure]
import { config } from "../server/config.js";
import { health, chatJSON, getProfile } from "../server/llm.js";

const id = process.argv[2] || config.llmProfile;
const L = getProfile(id);
if (!L) { console.log(`✗ No existe el perfil «${id}». Usa local o azure.`); process.exit(1); }
if (!L.configured) { console.log(`✗ ${L.label} no está configurado en .env.`); process.exit(1); }
console.log(`Perfil: ${L.label} · ${L.baseUrl}`);
console.log(`Intérprete: ${L.routerModel} (${L.routerReasoning || "por defecto"}) · Compositor: ${L.composerModel} (${L.composerReasoning || "por defecto"})\n`);

const h = await health(L);
if (!h.reachable) {
  console.log(`✗ No hay respuesta de ${L.baseUrl}.`);
  console.log(L.provider === "ollama" ? "  Abre la app de Ollama o ejecuta: ollama serve" : "  Arranca tu servidor compatible con OpenAI.");
  process.exit(1);
}
console.log(L.provider === "azure" ? "✓ Configurado" : "✓ El servidor responde");
if (h.missing.length) {
  console.log(`✗ Faltan modelos: ${h.missing.join(", ")}`);
  if (L.provider === "ollama") console.log(`  Ejecuta: ${h.missing.map(m => `ollama pull ${m}`).join(" && ")}`);
  process.exit(1);
}
if (L.provider !== "azure") console.log("✓ Modelos disponibles");

for (const [rol, model, reasoning] of [["Intérprete", L.routerModel, L.routerReasoning], ["Compositor", L.composerModel, L.composerReasoning]]) {
  process.stdout.write(`… Probando ${rol} (${model}) `);
  try {
    const { value, seconds } = await chatJSON({ model, reasoning, profile: L, label: "check", prompt: 'Responde SOLO con este JSON, sin nada más: {"ok": true, "saludo": "hola desde Eidos"}' });
    console.log(`\r✓ ${rol} responde JSON en ${seconds.toFixed(1)} s: ${JSON.stringify(value)}`);
  } catch (e) {
    console.log(`\r✗ ${rol}: ${e.message}`);
    if (e.raw) console.log(`  Respuesta recibida: ${String(e.raw).slice(0, 300)}`);
    process.exit(1);
  }
  if (model === L.composerModel && L.routerModel === L.composerModel && reasoning === L.composerReasoning) break;
}
console.log("\nTodo listo. Arranca con: npm start");
