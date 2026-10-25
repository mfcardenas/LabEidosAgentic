// El bucle del runtime: Intérprete → Caché → Compositor → Guardián → Datos → (Renderizador en el navegador).
// Cada paso se emite como evento de traza para que la interfaz muestre qué hizo cada agente.
import { chatJSON, LLMError, activeProfile } from "./llm.js";
import { loadSpecs, intentInfo } from "./specs.js";
import { guard, GuardError } from "./guard.js";
import { composerPrompt, routerPrompt } from "./prompts.js";

export function slug(s) {
  return String(s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) || "vista";
}

function tracer(emit) {
  let seq = 0;
  return (kind, text) => {
    const id = ++seq, t0 = Date.now();
    emit({ type: "trace", id, kind, text, status: "run" });
    const fin = (status, t, details) => emit({ type: "trace", id, kind, text: t ?? text, status, ms: Date.now() - t0, details: details?.length ? details : undefined });
    return { done: (t, d) => fin("done", t, d), fail: (t, d) => fin("fail", t, d) };
  };
}

const errText = e => (e instanceof LLMError || e instanceof GuardError ? e.message : `Error inesperado: ${e?.message || e}`);

export function makeRuntime(store, data) {

  function sanitizeParams(info, p = {}) {
    const E = info.entity, out = {};
    if (["listado", "libre"].includes(info.tipo) && p.filter) { const f = data.normFilter(E, p.filter); if (Object.keys(f).length) out.filter = f; }
    if (["detalle", "edicion", "baja"].includes(info.tipo)) out.id = String(p.id ?? "");
    if (["alta", "edicion"].includes(info.tipo) && p.prefill) { const pf = data.cleanPrefill(E, p.prefill); if (Object.keys(pf).length) out.prefill = pf; }
    if (info.tipo === "libre") out.key = slug(p.key || "vista");
    return out;
  }
  const keyFor = (info, params) => (info.tipo === "libre" ? `custom.${params.key}` : info.name);

  function summary(info, ctx) {
    if (ctx.items) return `${ctx.count} de ${ctx.stats.total ?? ctx.count} registros${ctx.filter.active ? ` · ${ctx.filter.label}` : ""}`;
    const t = ctx.item?.[info.entity.campoTitulo];
    return t ? String(t) : `Borrador de ${info.entity.etiqueta}`;
  }

  async function compose(specs, info, { brief, title }, step, emit, signal) {
    const L = activeProfile();
    const prompt = extra => composerPrompt(specs, info, { brief, title, ...extra });
    const call = async (label, extra) => {
      const s = step("composer", label);
      try {
        const r = await chatJSON({ model: L.composerModel, reasoning: L.composerReasoning, prompt: prompt(extra), signal, label: "compositor", profile: L });
        s.done(`Plantilla propuesta en ${r.seconds.toFixed(1)} s · ${L.composerModel}`);
        return { raw: r.value, seconds: r.seconds };
      } catch (e) {
        if (e.code === "invalid_json") { s.fail("No devolvió un JSON válido"); return { invalid: e.message }; }
        s.fail(errText(e));
        emit({ type: "error", code: e.code || "error", message: errText(e) });
        return null;
      }
    };
    const review = (raw, label) => {
      const g = step("guard", label);
      try {
        const out = guard(raw, info, specs);
        const details = [...out.fixes, ...out.warnings.map(w => `Aviso: ${w}`)];
        g.done(out.fixes.length ? `Válida con ${out.fixes.length} corrección(es) · ${out.nodes} nodos` : `Válida sin cambios · ${out.nodes} nodos`, details);
        return { out };
      } catch (e) {
        if (!(e instanceof GuardError)) throw e;
        g.fail(`Rechazada: ${e.message}`);
        return { invalid: e.message };
      }
    };

    let first = await call(`Diseñando ${info.name}${brief ? ` · «${brief}»` : ""}`);
    if (!first) return null;
    let seconds = first.seconds || 0;
    let checked = first.raw !== undefined ? review(first.raw, "Revisando contra catálogo y spec") : { invalid: first.invalid };
    if (checked.out) return { ...checked.out, seconds };

    const second = await call("Corrigiendo la plantilla", { previousError: checked.invalid });
    if (!second) return null;
    seconds += second.seconds || 0;
    checked = second.raw !== undefined ? review(second.raw, "Revisando la corrección") : { invalid: second.invalid };
    if (checked.out) return { ...checked.out, seconds };
    emit({ type: "error", code: "invalid_template", message: "El Compositor no consiguió una plantilla válida. Prueba a regenerarla o sube el esfuerzo de razonamiento." });
    return null;
  }

  async function navigate(nav, opts, emit, signal, step = tracer(emit)) {
    const L = activeProfile();
    const { regenerate = false, auto = true } = opts || {};
    const specs = loadSpecs();
    const info = intentInfo(specs, nav?.intent);
    if (!info) { emit({ type: "error", code: "bad_intent", message: `El intent «${nav?.intent}» no existe en la spec.` }); return; }
    const params = sanitizeParams(info, nav.params);
    const key = keyFor(info, params);
    const navOut = { intent: info.name, params, key };

    const d = step("data", `Contexto para ${info.name}`);
    const ctx = data.context(info, params);
    if (ctx.missing) { d.fail(`Ese ${info.entity.etiqueta} ya no existe`); emit({ type: "gone", nav: navOut, message: `Ese ${info.entity.etiqueta} ya no existe. Puede que alguien lo haya dado de baja.` }); return; }
    d.done(summary(info, ctx));

    const c = step("cache", `Busca plantilla «${key}»`);
    const stored = store.getScreen(key);
    const fresh = stored && stored.specVersion === specs.version ? stored : null;
    if (fresh && !regenerate) {
      c.done(`Acierto: reutiliza «${key}», sin llamar a ningún modelo`);
      emit({ type: "result", nav: navOut, screen: fresh, fromCache: true, context: ctx, entity: info.entidad, tipo: info.tipo });
      return;
    }
    c.done(regenerate ? "Se pide una plantilla nueva" : stored ? "Había una plantilla, pero de otra versión de las specs" : `No hay plantilla para «${key}»`);
    if (!auto) { emit({ type: "missing", nav: navOut }); return; }

    // La petición textual solo guía a las vistas libres: el resto de plantillas se reutilizan con
    // cualquier dato, así que no deben heredar «alta de Marta» ni un título concreto.
    const libre = info.tipo === "libre";
    const brief = libre ? (opts?.brief ?? stored?.brief ?? null) : null;
    const title = libre ? (opts?.title ?? stored?.title ?? null) : null;
    emit({ type: "working", nav: navOut, text: `El Compositor (${L.composerModel}) está diseñando esta pantalla a partir de las specs.` });
    const out = await compose(specs, info, { brief, title }, step, emit, signal);
    if (!out) return;
    const doc = {
      key, intent: info.name, specVersion: specs.version, template: out.tpl, fixes: out.fixes, nodes: out.nodes,
      brief, title: title || out.tpl.title || null, model: L.composerModel, seconds: out.seconds, createdAt: new Date().toISOString()
    };
    store.saveScreen(doc);
    step("cache", `Guardada «${key}» para reutilizarla`).done();
    emit({ type: "result", nav: navOut, screen: doc, fromCache: false, context: data.context(info, params), entity: info.entidad, tipo: info.tipo });
  }

  async function ask(text, current, emit, signal) {
    const L = activeProfile();
    const specs = loadSpecs();
    const step = tracer(emit);
    const s = step("router", `«${String(text).slice(0, 120)}»`);
    const customViews = listScreens().filter(d => d.key.startsWith("custom.") && !d.stale);
    let r, seconds;
    try {
      ({ value: r, seconds } = await chatJSON({
        model: L.routerModel, reasoning: L.routerReasoning, signal, label: "interprete", profile: L,
        prompt: routerPrompt(specs, data, { text, current, customViews })
      }));
    } catch (e) {
      s.fail(errText(e));
      emit({ type: "note", who: "Intérprete", text: errText(e), error: true });
      emit({ type: "idle" });
      return;
    }
    const info = r && typeof r === "object" ? intentInfo(specs, r.intent) : null;
    if (!info) {
      s.done(`No lo convierte en pantalla (${seconds.toFixed(1)} s)`);
      emit({ type: "note", who: "Intérprete", text: (r && r.reply) || "Eso no lo puedo resolver con esta app." });
      emit({ type: "idle" });
      return;
    }
    const params = sanitizeParams(info, { ...(r.params || {}), key: r.params?.key || r.key || r.title || text });
    if (params.id !== undefined && !data.all(info.entity).some(x => x.id === params.id)) {
      s.done(`No encuentra el registro (${seconds.toFixed(1)} s)`);
      emit({ type: "note", who: "Intérprete", text: `No encuentro ese ${info.entity.etiqueta} en la base de datos.` });
      emit({ type: "idle" });
      return;
    }
    s.done(`→ ${info.name} ${Object.keys(params).length ? JSON.stringify(params) : ""} · ${seconds.toFixed(1)} s`);
    if (r.reply) emit({ type: "note", who: "Intérprete", text: String(r.reply).slice(0, 240) });
    emit({ type: "nav", nav: { intent: info.name, params } });
    await navigate({ intent: info.name, params },
      { brief: r.brief ? String(r.brief).slice(0, 300) : String(text).slice(0, 300), title: r.title ? String(r.title).slice(0, 40) : null },
      emit, signal, step);
  }

  function listScreens() {
    const version = loadSpecs().version;
    return store.listScreens().map(d => ({ key: d.key, intent: d.intent, title: d.title, brief: d.brief, model: d.model, seconds: d.seconds, createdAt: d.createdAt, stale: d.specVersion !== version }));
  }

  return { navigate, ask, listScreens, slug };
}
