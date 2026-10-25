"""Patrones base: receta para el compositor, modelo de datos de la vista y plantilla de respaldo determinista.

Todo se deriva de la especificación de la aplicación; aquí no hay conocimiento de ningún dominio (F1).
"""
from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ..contracts import CompiledSpec, EntitySpec, ViewSpec

BASE_DIR = Path(__file__).parent


@cache
def base_patterns() -> dict[str, dict[str, Any]]:
    out = {}
    for file in sorted(BASE_DIR.glob("*.yaml")):
        data = yaml.safe_load(file.read_text(encoding="utf-8"))
        out[data["nombre"]] = data
    return out


# ---------------------------------------------------------------- vocabulario de una vista

def related_views(spec: CompiledSpec, entity: str) -> dict[str, str]:
    """Vistas de la misma entidad por rol: list, detail, create, edit, delete."""
    out: dict[str, str] = {}
    for v in spec.views.values():
        if v.entidad != entity:
            continue
        cmd = spec.commands.get(v.comando) if v.comando else None
        role = {"collection": "list", "record": "detail", "confirm": "delete"}.get(v.patron)
        if v.patron == "form" and cmd:
            role = "create" if cmd.tipo == "crear" else "edit"
        if role and role not in out:
            out[role] = v.id
    return out


def vocabulary(spec: CompiledSpec, view: ViewSpec) -> dict[str, str]:
    e = spec.entities[view.entidad]
    rel = related_views(spec, view.entidad)
    cmd = spec.commands.get(view.comando) if view.comando else None
    delete_cmd = spec.commands.get(spec.views[rel["delete"]].comando or "") if "delete" in rel else None
    nuevo = f"{'Nueva' if e.genero == 'f' else 'Nuevo'} {e.etiqueta}"
    submit = (cmd.etiqueta if cmd and cmd.etiqueta else
              f"Crear {e.etiqueta}" if cmd and cmd.tipo == "crear" else "Guardar cambios")
    return {
        "titulo": view.titulo, "etiqueta": e.etiqueta, "plural": e.plural, "Plural": e.plural[:1].upper() + e.plural[1:],
        "nuevo": nuevo, "eliminar": (delete_cmd.etiqueta if delete_cmd and delete_cmd.etiqueta else f"Eliminar {e.etiqueta}"),
        "campo_titulo": e.campoTitulo, "comando": view.comando or "", "submit": submit,
    }


def recipe(spec: CompiledSpec, view: ViewSpec) -> list[str]:
    lines = spec.recipes.get(view.patron) or base_patterns()[view.patron]["receta"]
    voc = vocabulary(spec, view)
    return [line.format_map(voc) for line in lines]


# ---------------------------------------------------------------- modelo de datos

def _field_schema(tipo: str) -> dict[str, Any]:
    return {"type": {"numero": "number", "booleano": "boolean"}.get(tipo, "string")}


def record_schema(e: EntitySpec) -> dict[str, Any]:
    props: dict[str, Any] = {"id": {"type": "string"}}
    for name, f in e.campos.items():
        props[name] = _field_schema(f.tipo) | {"x-field": f.tipo}
        if f.tipo == "referencia":
            props[f"{name}_titulo"] = {"type": "string", "x-field": "texto"}
    return {"type": "object", "properties": props}


def data_model_schema(spec: CompiledSpec, view: ViewSpec) -> dict[str, Any]:
    e = spec.entities[view.entidad]
    rec = record_schema(e)
    roots = base_patterns()[view.patron]["datos"]
    props: dict[str, Any] = {}
    if "items" in roots:
        props["items"] = {"type": "array", "items": rec}
        props["row"] = rec
    if "count" in roots:
        props["count"] = {"type": "integer"}
    if "filter" in roots:
        props["filter"] = {"type": "object", "properties": {"active": {"type": "boolean"}, "label": {"type": "string"}, "q": {"type": "string"}}
                           | {k: _field_schema(f.tipo) for k, f in e.campos.items()}}
    if "stats" in roots:
        props["stats"] = {"type": "object", "properties": {
            k: ({"type": "array", "items": {"type": "object", "properties": {"label": {"type": "string"}, "value": {"type": "integer"}}}}
                if m.tipo == "reparto" else {"type": "integer"})
            for k, m in e.metricas.items()}}
    if "item" in roots:
        props["item"] = rec
    if "options" in roots:
        props["options"] = {"type": "object", "properties": {
            k: {"type": "array", "items": {"type": "object", "properties": {"value": {"type": "string"}, "label": {"type": "string"}}}}
            for k, f in e.campos.items() if f.tipo in ("enum", "referencia")}}
    return {"type": "object", "properties": props}


def resolve_path(schema: dict[str, Any], path: str) -> dict[str, Any] | None:
    node: dict[str, Any] | None = schema
    for seg in path.strip("/").split("/"):
        if node is None:
            return None
        if node.get("type") == "array":
            node = node.get("items") if seg.isdigit() else None
        elif node.get("type") == "object":
            node = node.get("properties", {}).get(seg)
        else:
            return None
    return node


def describe_data_model(schema: dict[str, Any]) -> str:
    """Resumen legible del modelo de datos para el prompt."""
    def fmt(node: dict[str, Any]) -> str:
        if node.get("type") == "object":
            return "{" + ", ".join(f"{k}: {fmt(v)}" for k, v in node.get("properties", {}).items()) + "}"
        if node.get("type") == "array":
            return f"[{fmt(node.get('items', {}))}]"
        return node.get("x-field") or node.get("type", "valor")
    return "\n".join(f"/{k}: {fmt(v)}" for k, v in schema["properties"].items())


# ---------------------------------------------------------------- plantilla de respaldo

_FORMAT = {"enum": "badge", "booleano": "status", "fecha": "date", "fechahora": "datetime", "email": "email", "numero": "number"}


def _fmt(e: EntitySpec, field: str) -> str:
    f = e.campos.get(field)
    return _FORMAT.get(f.tipo, "text") if f else "text"


def _display(e: EntitySpec, name: str) -> str:
    return f"{name}_titulo" if e.campos[name].tipo == "referencia" else name


def fallback(spec: CompiledSpec, view: ViewSpec) -> dict[str, Any]:
    """Documento de pantalla determinista y válido para cualquier vista de los patrones base."""
    e = spec.entities[view.entidad]
    rel = related_views(spec, view.entidad)
    voc = vocabulary(spec, view)
    comps: list[dict[str, Any]] = []
    item_id = {"path": "/item/id"}
    title_field = e.campoTitulo
    others = [k for k in e.campos if k != title_field]
    page: dict[str, Any] = {"id": "page", "component": "Page", "title": view.titulo, "actions": [], "children": []}
    comps.append(page)

    def add(c: dict[str, Any], parent: dict[str, Any] | None = None, slot: str = "children") -> dict[str, Any]:
        comps.append(c)
        (parent or page)[slot].append(c["id"])
        return c

    if view.patron == "collection":
        page["subtitle"] = {"template": f"${{/count}} {e.plural}"}
        if "create" in rel:
            add({"id": "create", "component": "Button", "label": voc["nuevo"], "variant": "primary",
                 "action": {"function": "navigate", "args": {"view": rel["create"]}}}, slot="actions")
        counts = [k for k, m in e.metricas.items() if m.tipo in ("conteo", "recientes")][:4]
        if counts:
            stats = add({"id": "stats", "component": "Columns", "children": []})
            for k in counts:
                add({"id": f"stat-{k.lower()}", "component": "Stat", "label": e.metricas[k].etiqueta, "value": {"path": f"/stats/{k}"}}, stats)
        add({"id": "filter-info", "component": "Alert", "tone": "info", "text": {"path": "/filter/label"}, "visible": {"path": "/filter/active"}})
        add({"id": "clear-filter", "component": "Button", "label": "Quitar filtro", "variant": "ghost",
             "action": {"function": "navigate", "args": {"view": view.id}}, "visible": {"path": "/filter/active"}})
        card = add({"id": "list-card", "component": "Card", "title": voc["Plural"], "children": []})
        cols = [{"field": title_field, "label": e.campos[title_field].etiqueta, "format": "person"}]
        cols += [{"field": _display(e, k), "label": e.campos[k].etiqueta, "format": _fmt(e, k)} for k in others[:4]]
        table: dict[str, Any] = {"id": "list", "component": "Table", "rows": {"path": "/items"}, "columns": cols, "visible": {"path": "/count"}}
        if "detail" in rel:
            table["rowAction"] = {"function": "navigate", "args": {"view": rel["detail"], "params": {"id": {"path": "/row/id"}}}}
        add(table, card)
        add({"id": "empty", "component": "Empty", "title": f"No hay {e.plural}", "text": "Prueba con otro filtro o quítalo para ver todos.",
             "visible": {"not": {"path": "/count"}}})

    elif view.patron == "record":
        page["title"] = {"path": f"/item/{title_field}"}
        if "edit" in rel:
            add({"id": "edit", "component": "Button", "label": "Editar", "variant": "primary",
                 "action": {"function": "navigate", "args": {"view": rel["edit"], "params": {"id": item_id}}}}, slot="actions")
        if "delete" in rel:
            add({"id": "delete", "component": "Button", "label": voc["eliminar"], "variant": "secondary",
                 "action": {"function": "navigate", "args": {"view": rel["delete"], "params": {"id": item_id}}}}, slot="actions")
        half = max(1, (len(others) + 1) // 2)
        cols = add({"id": "cols", "component": "Columns", "children": []})
        for cid, title, fields in [("main", "Datos", [title_field, *others[:half - 1]]), ("extra", "Estado", others[half - 1:])]:
            if not fields:
                continue
            card = add({"id": f"{cid}-card", "component": "Card", "title": title, "children": []}, cols)
            add({"id": f"{cid}-kv", "component": "KeyValue", "items": [
                {"label": e.campos[k].etiqueta, "value": {"path": f"/item/{_display(e, k)}"}, "format": _fmt(e, k)} for k in fields]}, card)

    elif view.patron == "form":
        cmd = spec.commands[view.comando or ""]
        page["subtitle"] = f"Completa los datos {'de la' if e.genero == 'f' else 'del'} {e.etiqueta}."
        back = rel.get("detail") if cmd.tipo == "actualizar" else rel.get("list")
        card = add({"id": "form-card", "component": "Card", "title": "Datos", "children": []})
        form: dict[str, Any] = {"id": "form", "component": "Form", "command": cmd.id,
                                "fields": [{"field": k, "label": f.etiqueta} for k, f in e.campos.items() if f.editable],
                                "submit": {"label": voc["submit"]}}
        if back:
            args: dict[str, Any] = {"view": back}
            if cmd.tipo == "actualizar":
                args["params"] = {"id": item_id}
            form["cancel"] = {"label": "Cancelar", "action": {"function": "navigate", "args": args}}
        add(form, card)
        rules = [spec.rules[r].texto for r in e.reglas if r in spec.rules]
        if rules:
            add({"id": "rules", "component": "Text", "variant": "muted", "value": " ".join(rules)})

    elif view.patron == "confirm":
        page["subtitle"] = {"path": f"/item/{title_field}"}
        if "detail" in rel:
            add({"id": "cancel", "component": "Button", "label": "Cancelar", "variant": "ghost",
                 "action": {"function": "navigate", "args": {"view": rel["detail"], "params": {"id": item_id}}}}, slot="actions")
        add({"id": "confirm", "component": "Button", "label": voc["eliminar"], "variant": "danger",
             "action": {"command": view.comando or "", "input": {"id": item_id}}}, slot="actions")
        add({"id": "warning", "component": "Alert", "tone": "danger", "title": "No se puede deshacer",
             "text": f"Se eliminará {'la' if e.genero == 'f' else 'el'} {e.etiqueta} y su información."})
        card = add({"id": "summary-card", "component": "Card", "title": e.etiqueta[:1].upper() + e.etiqueta[1:], "children": []})
        add({"id": "summary", "component": "KeyValue", "items": [
            {"label": e.campos[k].etiqueta, "value": {"path": f"/item/{_display(e, k)}"}, "format": _fmt(e, k)} for k in [title_field, *others[:3]]]}, card)

    return {"contract": "eidos-ui/1", "view": view.id, "root": "page", "components": comps}


def fingerprint_recipe(spec: CompiledSpec, pattern: str) -> str:
    import hashlib
    lines = spec.recipes.get(pattern) or base_patterns()[pattern]["receta"]
    return hashlib.sha256(json.dumps(lines, ensure_ascii=False).encode()).hexdigest()[:12]
