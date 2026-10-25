// Prompts de los dos agentes con IA. Se construyen enteros a partir de las specs:
// si cambias una spec, cambia lo que leen los agentes.
import { TIPOS } from "./specs.js";

const CTX_DOC = {
  items: E => `array de ${E.nombreInterno} {id, ${Object.keys(E.campos).join(", ")}}, ya filtrado y ordenado por ${E.orden || E.campoTitulo}`,
  count: () => "número de elementos en items",
  filter: () => "{active: boolean, label: texto legible del filtro aplicado, …campos filtrados}",
  stats: E => `métricas calculadas sobre TODOS los registros: {${Object.entries(E.metricas || {}).map(([k, m]) => `${k}${m.tipo === "reparto" ? ": [{label, value}]" : ": número"}`).join(", ")}}`,
  item: E => `un ${E.nombreInterno} {id, ${Object.keys(E.campos).join(", ")}}; en un alta es un borrador con valores por defecto`,
  options: E => `valores posibles de los campos enum: {${Object.keys(E.campos).filter(k => E.campos[k].tipo === "enum").map(k => `${k}: [{value, label}]`).join(", ")}}`
};

function exampleRecord(E) {
  const r = { id: "abc123" };
  for (const [k, d] of Object.entries(E.campos)) {
    if (d.tipo === "enum") r[k] = d.valores[0].valor;
    else if (d.tipo === "booleano") r[k] = true;
    else if (d.tipo === "fecha") r[k] = "2026-03-14";
    else if (d.tipo === "email") r[k] = "nombre@ejemplo.com";
    else r[k] = `${d.etiqueta} de ejemplo`;
  }
  return r;
}

export function composerPrompt(specs, info, { brief, title, previousError } = {}) {
  const E = info.entity;
  const roots = info.tipoInfo.contexto;
  const nav = Object.entries(specs.app.intents).map(([k, v]) => `- ${k} (${v.tipo}): ${v.descripcion} params: ${TIPOS[v.tipo].params}`).join("\n");
  const { nombreInterno, ...entitySpec } = E;
  return `Eres el Compositor de Eidos. En Eidos la app no tiene pantallas programadas: solo existen sus especificaciones, y tú generas cada pantalla cuando alguien la necesita.

Tu salida es una PLANTILLA de pantalla en JSON. No ves los datos reales: los enlazas con {{ruta}} o {"$bind":"ruta"} y el runtime los rellena cada vez que se muestra. La misma plantilla se reutilizará con otros datos (otro registro, otro filtro), así que no escribas nunca valores concretos de datos.

PANTALLA A GENERAR
intent: ${info.name}
tipo: ${info.tipo}
qué es: ${info.descripcion}
${brief ? `lo que pidió la persona: ${brief}\n` : ""}${title ? `título sugerido: ${title}\n` : ""}
CONTEXTO QUE PUEDES ENLAZAR (solo estas raíces: ${roots.join(", ")})
${roots.map(r => `- ${r}: ${CTX_DOC[r](E)}`).join("\n")}
Forma de un registro (valores inventados, solo para ver los tipos): ${JSON.stringify(exampleRecord(E))}

SPEC DE LA ENTIDAD ${E.nombreInterno}
${JSON.stringify(entitySpec)}

INTENTS A LOS QUE PUEDES NAVEGAR
${nav}
Flujos tras guardar: ${JSON.stringify(specs.app.flujos)}

CATÁLOGO (único vocabulario permitido; cualquier otro tipo o propiedad se descarta)
${JSON.stringify(specs.catalog)}

FORMA DE CADA NODO
Cada nodo es un objeto plano: {"type":"Componente", …sus props, "when"?, "children"?}. Las props del catálogo van directamente en el nodo, NUNCA dentro de una clave "props". {"$bind":"ruta"} es un objeto JSON, no una cadena.
Ejemplo: {"type":"Table","when":"count","rows":{"$bind":"items"},"columns":[{"field":"campo","label":"Campo","format":"text"}]}

REGLAS DE DISEÑO
Tono: ${specs.design.tono}
${specs.design.reglas.map(r => `- ${r}`).join("\n")}
${specs.design.recetas?.[info.tipo] ? `\nRECETA PARA ESTA PANTALLA (${info.tipo}); síguela salvo que la petición pida otra cosa:\n${specs.design.recetas[info.tipo].map((r, i) => `${i + 1}. ${r}`).join("\n")}\n` : ""}
${previousError ? `\nTU RESPUESTA ANTERIOR SE RECHAZÓ: ${previousError}\nDevuelve una plantilla válida.\n` : ""}
Responde SOLO con el JSON de la pantalla, sin texto alrededor ni bloques de código. Raíz: {"type":"Screen","title":"…","subtitle":"…","actions":[…],"children":[…]}`;
}

export function routerPrompt(specs, data, { text, current, customViews }) {
  const intents = Object.entries(specs.app.intents).map(([k, v]) => {
    let p = TIPOS[v.tipo].params;
    if (v.tipo === "libre") p += `; añade "title" (1-3 palabras) y "brief" (qué debe mostrar, 1-2 frases). Solo si ningún otro intent encaja`;
    return `- ${k} (${v.tipo}, ${v.entidad}): ${v.descripcion} params: ${p}`;
  }).join("\n");
  const entities = Object.keys(specs.app.entidades).map(name => {
    const E = { ...specs.app.entidades[name], nombreInterno: name };
    const fields = Object.entries(E.campos).map(([k, d]) => `${k} (${d.tipo}${d.tipo === "enum" ? `: ${d.valores.map(v => `"${v.valor}"`).join(" | ")}` : ""})`).join(", ");
    const rows = data.all(E).slice(0, 100).map(r => [r.id, ...Object.keys(E.campos).map(k => r[k] ?? "-")].join(" | ")).join("\n");
    const en = Object.entries(E.campos).find(([, d]) => d.tipo === "enum");
    const bo = Object.entries(E.campos).find(([, d]) => d.tipo === "booleano");
    const ex = { ...(en ? { [en[0]]: en[1].valores[0].valor } : {}), ...(bo ? { [bo[0]]: false } : {}) };
    return `ENTIDAD ${name} — campos: ${fields}
filter es SIEMPRE un objeto JSON {campo: valor}, nunca un texto. Incluye TODAS las condiciones de la petición a la vez, p. ej. ${JSON.stringify({ filter: ex })}.
Enum: el valor exacto de la lista (no la etiqueta ni el plural). Booleano: true o false sin comillas. Para buscar por nombre, email u otro texto usa q: {"q":"texto"}.
prefill admite los campos editables, con los mismos tipos.
Registros (id | ${Object.keys(E.campos).join(" | ")}):
${rows || "(ninguno)"}`;
  }).join("\n\n");
  return `Eres el Intérprete de Eidos, una app cuyas pantallas genera otro agente a demanda. Conviertes el mensaje de la persona en UNA navegación a un intent de la spec. Tú nunca cambias datos: altas, ediciones y bajas se confirman en su pantalla.

INTENTS
${intents}

VISTAS LIBRES YA EXISTENTES (si la petición es la misma idea, reutiliza su key exacta):
${customViews.length ? customViews.map(d => `- key "${d.key.replace(/^custom\./, "")}": ${d.title || ""} — ${d.brief || ""}`).join("\n") : "(ninguna)"}

PANTALLA ACTUAL: ${current ? `${current.intent} ${JSON.stringify(current.params || {})}` : "ninguna"}

${entities}

Si la petición no tiene que ver con esta app, o no puedes identificar el registro, usa intent "none".
Responde SOLO con JSON, sin texto alrededor: {"intent":"…","params":{…},"title":"…","brief":"…","reply":"una frase corta en español, tuteando, que diga qué vas a mostrar en términos del negocio (nunca hables de pantallas, plantillas, agentes ni de generar nada)"}

MENSAJE: «${String(text).slice(0, 500)}»`;
}
