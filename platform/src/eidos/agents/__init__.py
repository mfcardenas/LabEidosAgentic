"""Agentes con modelo. Sus prompts se construyen a partir de contratos y especificación (F3); nunca con datos reales (RP-07)."""
from __future__ import annotations

import json
from typing import Any

from ..catalog import DOCUMENT_CONTRACT, Catalog
from ..contracts import CompiledSpec, Finding, ViewSpec
from ..llm import Profile, complete_json
from ..patterns import data_model_schema, describe_data_model, fallback, recipe, related_views


def _entity_summary(spec: CompiledSpec, name: str) -> str:
    e = spec.entities[name]
    parts = []
    for k, f in e.campos.items():
        extra = ""
        if f.tipo == "enum":
            extra = " (" + " | ".join(f"{v.valor}={v.etiqueta}" for v in f.valores) + ")"
        elif f.tipo == "referencia":
            extra = f" → {f.entidad}; para mostrarlo usa {k}_titulo"
        flags = [x for x, on in (("obligatorio", f.requerido), ("solo lectura", not f.editable), ("único", f.unico)) if on]
        parts.append(f"  - {k}: {f.tipo} «{f.etiqueta}»{extra}{' [' + ', '.join(flags) + ']' if flags else ''}")
    metrics = "; ".join(f"{k}: {m.etiqueta} ({m.tipo})" for k, m in e.metricas.items())
    return (f"{e.entidad} («{e.etiqueta}», plural «{e.plural}», campo título {e.campoTitulo})\n" + "\n".join(parts)
            + (f"\n  Métricas en /stats: {metrics}" if metrics else ""))


def composer_prompt(spec: CompiledSpec, view: ViewSpec, catalog: Catalog, findings: list[Finding] | None = None) -> str:
    e = spec.entities[view.entidad]
    rel = related_views(spec, view.entidad)
    nav = "\n".join(f"- {vid}: {spec.views[vid].titulo} ({spec.views[vid].patron})" + (" · requiere params.id" if spec.views[vid].parametros.id else "")
                    for vid in sorted(set(rel.values()) | {spec.app.inicio}))
    cmd = spec.commands.get(view.comando or "")
    rules = [spec.rules[r].texto for r in e.reglas if r in spec.rules]
    previous = ""
    if findings:
        previous = "\nTU PROPUESTA ANTERIOR TENÍA ESTOS PROBLEMAS. Corrígelos todos:\n" + "\n".join(f"- [{f.code}] {f.message} {f.path}" for f in findings) + "\n"
    return f"""Eres el Compositor de {spec.app.nombre}. Diseñas UNA pantalla como documento JSON que un renderizador pinta con un catálogo cerrado de componentes.
No escribes datos: enlazas rutas del modelo de datos con {{"path": "/ruta"}} o textos con {{"template": "Hay ${{/count}} …"}}.

APLICACIÓN: {spec.app.proposito}

PANTALLA
- vista: {view.id} · patrón: {view.patron} · título: {view.titulo}
- qué es: {view.descripcion}
{f"- comando: {cmd.id} ({cmd.tipo})" if cmd else ""}

ENTIDAD
{_entity_summary(spec, view.entidad)}
{("Reglas de negocio: " + " ".join(rules)) if rules else ""}

MODELO DE DATOS DE ESTA VISTA (solo puedes enlazar estas rutas; /row solo dentro de rowAction de una Table)
{describe_data_model(data_model_schema(spec, view))}

VISTAS A LAS QUE PUEDES NAVEGAR
{nav}

RECETA DEL PATRÓN {view.patron} (síguela)
{chr(10).join(f"{i + 1}. {line}" for i, line in enumerate(recipe(spec, view)))}

TONO
{spec.voice.tono}
{chr(10).join(f"- {r}" for r in spec.voice.reglas)}

CATÁLOGO (único vocabulario permitido)
{catalog.prompt()}

FORMATO DEL DOCUMENTO
- {{"contract": "{DOCUMENT_CONTRACT}", "view": "{view.id}", "root": "<id del Page>", "components": [ ... ]}}
- components es una LISTA PLANA. Cada componente tiene "id" (kebab-case, único) y "component" (el nombre del catálogo, como texto). Los hijos se referencian por id en "children"; los botones de cabecera, en "actions" del Page.
- TODO id que aparezca en children o actions debe estar definido como un componente de la lista. Nunca escribas componentes dentro de children o actions.
- Las propiedades van directamente en el componente, nunca dentro de "props" ni anidadas bajo el nombre del componente.
- format va en el elemento (columna o item de KeyValue), nunca dentro de {{"path": …}}.
- Acciones: {{"function": "navigate", "args": {{"view": "<vista>", "params": {{"id": {{"path": "/item/id"}}}}}}}} o {{"command": "<comando>", "input": {{...}}}}.
- Ejemplo mínimo de forma (no de contenido): {{"contract": "{DOCUMENT_CONTRACT}", "view": "x", "root": "page", "components": [{{"id": "page", "component": "Page", "title": "Título", "actions": ["go"], "children": ["card"]}}, {{"id": "go", "component": "Button", "label": "Abrir", "variant": "primary", "action": {{"function": "navigate", "args": {{"view": "x"}}}}}}, {{"id": "card", "component": "Card", "title": "Datos", "children": ["intro"]}}, {{"id": "intro", "component": "Text", "value": "Hola"}}]}}
{previous}
Responde SOLO con el JSON del documento."""


def compose(spec: CompiledSpec, view: ViewSpec, catalog: Catalog, profile: Profile, findings: list[Finding] | None = None) -> tuple[Any, dict[str, Any]]:
    prompt = composer_prompt(spec, view, catalog, findings)
    value, meta = complete_json(profile, "composer", prompt, schema=catalog.screen_schema(), fake=lambda: fallback(spec, view))
    return value, meta | {"prompt_chars": len(prompt)}


# ---------------------------------------------------------------- intérprete

INTERPRETER_SCHEMA = {
    "type": "object",
    "required": ["view", "reply"],
    "properties": {
        "view": {"type": "string"},
        "params": {"type": "object", "properties": {"filtro": {"type": "object"}, "prefill": {"type": "object"}}},
        "search": {"type": "object", "properties": {"text": {"type": "string"}}},
        "reply": {"type": "string"},
    },
}


def interpreter_prompt(spec: CompiledSpec, text: str, current: dict[str, Any] | None) -> str:
    views = "\n".join(
        f"- {v.id} ({v.patron}, {v.entidad}): {v.descripcion}"
        + "".join(f" · admite {p}" for p, on in (("filtro", v.parametros.filtro), ("prefill", v.parametros.prefill)) if on)
        + (" · necesita un registro concreto (usa search)" if v.parametros.id else "")
        for v in spec.views.values())
    entities = "\n".join(_entity_summary(spec, n) for n in spec.entities)
    return f"""Eres el Intérprete de {spec.app.nombre}: {spec.app.proposito}
Conviertes el mensaje de la persona en UNA navegación. Nunca cambias datos: altas, cambios y bajas se confirman en su pantalla.

VISTAS
{views}

ENTIDADES (no ves registros reales)
{entities}

REGLAS DE SALIDA
- filtro: objeto {{campo: valor}} con TODAS las condiciones; enum con su valor exacto; booleanos true/false; texto libre en "q".
- prefill: valores iniciales para un formulario, mismos tipos.
- Si la vista necesita un registro concreto, pon en search.text el texto que lo identifica (nombre, email…); el sistema lo buscará.
- reply: una frase corta en términos del negocio, sin hablar de pantallas ni de generar nada.
- Si la petición no tiene que ver con la aplicación, usa view "none".

VISTA ACTUAL: {json.dumps(current or {}, ensure_ascii=False)}

Responde SOLO con JSON: {{"view": "…", "params": {{…}}, "search": {{"text": "…"}}, "reply": "…"}}

MENSAJE: «{text[:500]}»"""


def interpret(spec: CompiledSpec, text: str, current: dict[str, Any] | None, profile: Profile) -> tuple[dict[str, Any], dict[str, Any]]:
    prompt = interpreter_prompt(spec, text, current)
    home = spec.views[spec.app.inicio]
    fake = lambda: {"view": home.id, "params": {"filtro": {"q": text}} if home.parametros.filtro else {}, "reply": "Esto es lo que he encontrado."}  # noqa: E731
    value, meta = complete_json(profile, "interpreter", prompt, schema=INTERPRETER_SCHEMA, fake=fake)
    return (value if isinstance(value, dict) else {}), meta
