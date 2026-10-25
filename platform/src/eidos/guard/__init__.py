"""Guardián: verificación determinista de documentos de pantalla (capas 1-3). Ver docs/02-arquitectura.md §3.2.

Las reglas son datos (catálogo, design_rules.yaml, especificación); aquí no hay condiciones por pantalla ni por dominio (F6).
"""
from __future__ import annotations

import copy
import json
import re
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ..catalog import DOCUMENT_CONTRACT, Catalog
from ..contracts import CompiledSpec, Finding, Severity, ViewSpec
from ..patterns import data_model_schema, resolve_path

TEMPLATE_REF = re.compile(r"\$\{(/[A-Za-z0-9_/]+)\}")


@cache
def default_design_rules() -> dict[str, Any]:
    return yaml.safe_load((Path(__file__).parent / "design_rules.yaml").read_text(encoding="utf-8"))


def _f(code: str, sev: Severity, layer: str, msg: str, path: str = "") -> Finding:
    return Finding(code=code, severity=sev, layer=layer, message=msg, path=path)


# ---------------------------------------------------------------- capa 0 · normalización (autocorrecciones)

def normalize(doc: Any) -> tuple[dict[str, Any], list[Finding]]:
    """Corrige desviaciones habituales del modelo sin cambiar la intención. Cada corrección queda registrada."""
    fixes: list[Finding] = []
    fix = lambda msg, path="": fixes.append(_f("AUTOFIX", Severity.AUTOFIXED, "normalize", msg, path))  # noqa: E731
    if not isinstance(doc, dict):
        return {"contract": DOCUMENT_CONTRACT, "components": []}, [_f("NOT_OBJECT", Severity.BLOCKING, "structure", "La respuesta no es un objeto JSON")]
    doc = copy.deepcopy(doc)
    if doc.get("contract") != DOCUMENT_CONTRACT:
        doc["contract"] = DOCUMENT_CONTRACT
    comps = doc.get("components")
    if not isinstance(comps, list):
        return doc, fixes

    def unstring(v: Any, path: str) -> Any:
        if isinstance(v, str) and v.strip().startswith("{") and ('"path"' in v or '"template"' in v):
            try:
                parsed = json.loads(v)
                fix("Enlace escrito como texto convertido a objeto", path)
                return parsed
            except json.JSONDecodeError:
                return v
        if isinstance(v, dict):
            return {k: unstring(x, f"{path}/{k}") for k, x in v.items()}
        if isinstance(v, list):
            return [unstring(x, f"{path}/{i}") for i, x in enumerate(v)]
        return v

    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            continue
        where = f"/components/{i}"
        if "component" not in c and "type" in c:
            c["component"] = c.pop("type")
            fix("«type» renombrado a «component»", where)
        nested = c.get("component")
        if isinstance(nested, dict):
            if isinstance(nested.get("type"), str):
                # {"component": {"type": "Card", ...props}}
                props = dict(nested)
                c["component"] = props.pop("type")
            elif len(nested) == 1 and isinstance(next(iter(nested.values())), dict):
                # Forma anidada de A2UI v0.8: {"component": {"Card": {...props}}}
                name, props = next(iter(nested.items()))
                c["component"] = name
            elif c.get("id") == doc.get("root"):
                props, c["component"] = dict(nested), "Page"
            else:
                props = None
            if props is not None:
                for k, v in props.items():
                    c.setdefault(k, v)
                fix("Componente anidado aplanado", where)
        if c.get("component") == "KeyValue" and isinstance(c.get("items"), list):
            for item in c["items"]:
                val = item.get("value") if isinstance(item, dict) else None
                if isinstance(val, dict) and "path" in val and "format" in val:
                    item.setdefault("format", val.pop("format"))
                    fix("«format» sacado del enlace al elemento de KeyValue", where)

    # Hijos o acciones escritos en línea en lugar de por id: se extraen a la lista plana.
    hoisted: list[dict[str, Any]] = []
    for c in comps:
        if not isinstance(c, dict):
            continue
        for slot in ("children", "actions"):
            if not isinstance(c.get(slot), list):
                continue
            refs = []
            for j, child in enumerate(c[slot]):
                if isinstance(child, dict) and ("component" in child or "type" in child):
                    child.setdefault("id", f"{c.get('id', 'c')}-{slot}-{j}")
                    hoisted.append(child)
                    refs.append(child["id"])
                    fix(f"Componente en línea extraído como «{child['id']}»", f"{c.get('id')}.{slot}")
                else:
                    refs.append(child)
            c[slot] = refs
    if hoisted:
        doc["components"] = comps + hoisted
        again, more = normalize(doc)
        return again, fixes + more

    for i, c in enumerate(comps):
        if not isinstance(c, dict):
            continue
        where = f"/components/{i}"
        if isinstance(c.get("props"), dict):
            props = c.pop("props")
            for k, v in props.items():
                c.setdefault(k, v)
            fix("Propiedades sacadas de «props»", where)
        if isinstance(c.get("id"), str) and not re.fullmatch(r"[a-z][a-z0-9-]*", c["id"]):
            new = re.sub(r"[^a-z0-9-]+", "-", c["id"].lower()).strip("-") or f"c{i}"
            new = new if new[0].isalpha() else f"c-{new}"
            for other in comps:
                if isinstance(other, dict):
                    for slot in ("children", "actions"):
                        if isinstance(other.get(slot), list):
                            other[slot] = [new if x == c["id"] else x for x in other[slot]]
            if doc.get("root") == c["id"]:
                doc["root"] = new
            fix(f"Id «{c['id']}» normalizado a «{new}»", where)
            c["id"] = new
        comps[i] = unstring(c, where)
    return doc, fixes


# ---------------------------------------------------------------- capa 1 · estructura

def verify_structure(doc: dict[str, Any], catalog: Catalog) -> list[Finding]:
    out: list[Finding] = []
    comps = doc.get("components")
    if not isinstance(comps, list) or not comps:
        return [_f("NO_COMPONENTS", Severity.BLOCKING, "structure", "El documento no tiene components")]
    seen: set[str] = set()
    for i, c in enumerate(comps):
        where = f"/components/{i}"
        if not isinstance(c, dict):
            out.append(_f("COMPONENT_NOT_OBJECT", Severity.BLOCKING, "structure", "Componente no es un objeto", where))
            continue
        name = c.get("component")
        if not isinstance(name, str) or name not in catalog.components:
            out.append(_f("COMPONENT_UNKNOWN", Severity.BLOCKING, "structure", f"«{str(name)[:60]}» no está en el catálogo", where))
            continue
        if not isinstance(c.get("id"), str):
            out.append(_f("ID_MISSING", Severity.BLOCKING, "structure", f"{name} sin id de texto", where))
            continue
        if c["id"] in seen:
            out.append(_f("DUPLICATE_ID", Severity.BLOCKING, "structure", f"Id duplicado «{c['id']}»", where))
        seen.add(c["id"])
        for err in sorted(catalog.validators[name].iter_errors(c), key=lambda e: list(e.path)):
            loc = "/".join(map(str, err.path))
            out.append(_f("SCHEMA", Severity.BLOCKING, "structure", f"{name}.{loc or '(raíz)'}: {err.message[:200]}", f"{where}/{loc}"))
    return out


# ---------------------------------------------------------------- capa 2 · grafo y enlaces

def _paths(value: Any) -> list[str]:
    if isinstance(value, dict):
        if isinstance(value.get("path"), str):
            return [value["path"]]
        if isinstance(value.get("template"), str):
            return TEMPLATE_REF.findall(value["template"])
        return [p for v in value.values() for p in _paths(v)]
    if isinstance(value, list):
        return [p for v in value for p in _paths(v)]
    return []


def verify_graph_and_bindings(doc: dict[str, Any], view: ViewSpec, spec: CompiledSpec, catalog: Catalog) -> list[Finding]:
    out: list[Finding] = []
    comps = {c["id"]: c for c in doc["components"] if isinstance(c, dict) and "id" in c}
    index = {c["id"]: i for i, c in enumerate(doc["components"]) if isinstance(c, dict) and "id" in c}
    root = comps.get(doc.get("root", ""))
    if not root or root.get("component") != "Page":
        out.append(_f("ROOT", Severity.BLOCKING, "graph", "root debe apuntar a un componente Page"))
    if sum(1 for c in comps.values() if c.get("component") == "Page") > 1:
        out.append(_f("ROOT_MULTIPLE", Severity.BLOCKING, "graph", "Solo puede haber un Page"))

    parents: dict[str, str] = {}
    for cid, c in comps.items():
        for slot in ("children", "actions"):
            for ref in c.get(slot, []) or []:
                if ref not in comps:
                    out.append(_f("REF_MISSING", Severity.BLOCKING, "graph", f"{cid}.{slot} referencia «{ref}», que no existe", f"/components/{index[cid]}/{slot}"))
                elif ref in parents:
                    out.append(_f("REF_SHARED", Severity.BLOCKING, "graph", f"«{ref}» tiene dos padres ({parents[ref]} y {cid})"))
                else:
                    parents[ref] = cid
                if slot == "actions" and ref in comps and comps[ref].get("component") != "Button":
                    out.append(_f("ACTION_NOT_BUTTON", Severity.BLOCKING, "graph", f"{cid}.actions solo admite Button («{ref}» no lo es)"))
            if slot == "children" and c.get("component") in catalog.components and not catalog.is_container(c["component"]) and c.get(slot):
                out.append(_f("NOT_CONTAINER", Severity.BLOCKING, "graph", f"{c['component']} no admite children"))
    if root:
        reachable, stack = set(), [root["id"]]
        while stack:
            cur = stack.pop()
            if cur in reachable or cur not in comps:
                if cur in reachable:
                    out.append(_f("CYCLE", Severity.BLOCKING, "graph", f"Ciclo en «{cur}»"))
                continue
            reachable.add(cur)
            stack.extend((comps[cur].get("children") or []) + (comps[cur].get("actions") or []))
        for cid in comps.keys() - reachable:
            out.append(_f("ORPHAN", Severity.MINOR, "graph", f"«{cid}» no cuelga de la pantalla y no se mostrará", f"/components/{index[cid]}"))

    schema = data_model_schema(spec, view)
    e = spec.entities[view.entidad]

    def check_path(p: str, where: str, row_scope: bool = False) -> dict[str, Any] | None:
        if p.startswith("/row/") and not row_scope:
            out.append(_f("BINDING_ROW_SCOPE", Severity.BLOCKING, "bindings", f"{p} solo es válido dentro de rowAction", where))
            return None
        node = resolve_path(schema, p)
        if node is None:
            out.append(_f("BINDING_UNKNOWN_PATH", Severity.BLOCKING, "bindings", f"La ruta {p} no existe en el modelo de datos de {view.id}", where))
        return node

    def check_navigate(action: dict[str, Any], where: str, row_scope: bool = False) -> None:
        args = action.get("args", {})
        target = spec.views.get(args.get("view", ""))
        if not target:
            out.append(_f("NAV_UNKNOWN_VIEW", Severity.BLOCKING, "bindings", f"Navega a la vista inexistente «{args.get('view')}»", where))
            return
        params = args.get("params") or {}
        if target.parametros.id and "id" not in params:
            out.append(_f("NAV_MISSING_ID", Severity.BLOCKING, "bindings", f"La vista {target.id} necesita params.id", where))
        for k in params:
            if k not in ("id", "filtro", "prefill"):
                out.append(_f("NAV_PARAM", Severity.BLOCKING, "bindings", f"Parámetro «{k}» no admitido por {target.id}", where))
        for p in _paths(params):
            check_path(p, where, row_scope)

    for cid, c in comps.items():
        where = f"/components/{index[cid]}"
        name = c.get("component")
        for key, val in c.items():
            if key in ("rowAction", "action", "cancel") or (name == "Table" and key == "rows") or (name == "BarList" and key == "items"):
                continue
            for p in _paths(val):
                check_path(p, f"{where}/{key}")
        if name == "Table":
            rows = c.get("rows", {}).get("path", "")
            node = check_path(rows, f"{where}/rows") if rows else None
            if node is not None and node.get("type") != "array":
                out.append(_f("TABLE_ROWS", Severity.BLOCKING, "bindings", f"{rows} no es una lista", f"{where}/rows"))
            item = (node or {}).get("items", {}).get("properties", {})
            for j, col in enumerate(c.get("columns", [])):
                if item and col.get("field") not in item:
                    out.append(_f("TABLE_COLUMN", Severity.BLOCKING, "bindings", f"La columna «{col.get('field')}» no es un campo de {e.entidad}", f"{where}/columns/{j}"))
            if isinstance(c.get("rowAction"), dict):
                check_navigate(c["rowAction"], f"{where}/rowAction", row_scope=True)
        if name == "BarList":
            node = check_path(c.get("items", {}).get("path", "/"), f"{where}/items")
            if node is not None and node.get("type") != "array":
                out.append(_f("BARLIST_ITEMS", Severity.BLOCKING, "bindings", "BarList.items debe enlazar una métrica de reparto", f"{where}/items"))
        action = c.get("action")
        if isinstance(action, dict):
            if action.get("function") == "navigate":
                check_navigate(action, f"{where}/action")
            elif "command" in action:
                if action["command"] not in spec.commands:
                    out.append(_f("COMMAND_UNKNOWN", Severity.BLOCKING, "bindings", f"Comando inexistente «{action['command']}»", f"{where}/action"))
                for p in _paths(action.get("input", {})):
                    check_path(p, f"{where}/action")
        if name == "Form":
            if c.get("command") != view.comando:
                out.append(_f("FORM_COMMAND", Severity.BLOCKING, "bindings", f"El formulario debe ejecutar «{view.comando}»", f"{where}/command"))
            for j, fld in enumerate(c.get("fields", [])):
                spec_field = e.campos.get(fld.get("field", ""))
                if not spec_field:
                    out.append(_f("FORM_FIELD", Severity.BLOCKING, "bindings", f"«{fld.get('field')}» no es un campo de {e.entidad}", f"{where}/fields/{j}"))
                elif not spec_field.editable:
                    out.append(_f("FORM_READONLY", Severity.BLOCKING, "bindings", f"«{fld.get('field')}» lo rellena el sistema", f"{where}/fields/{j}"))
            present = {fld.get("field") for fld in c.get("fields", [])}
            for k, fs in e.campos.items():
                if fs.requerido and fs.editable and k not in present:
                    out.append(_f("FORM_REQUIRED_MISSING", Severity.BLOCKING, "bindings", f"Falta el campo obligatorio «{k}»", f"{where}/fields"))
            if isinstance(c.get("cancel"), dict):
                check_navigate(c["cancel"].get("action", {}), f"{where}/cancel")
    return out


# ---------------------------------------------------------------- capa 3 · diseño

def verify_design(doc: dict[str, Any], view: ViewSpec, spec: CompiledSpec) -> list[Finding]:
    rules = default_design_rules() | (spec.design_rules or {})
    out: list[Finding] = []
    comps = [c for c in doc["components"] if isinstance(c, dict)]
    if len(comps) > rules["max_nodos"]:
        out.append(_f("MAX_NODES", Severity.MAJOR, "design", f"{len(comps)} componentes (máximo {rules['max_nodos']})"))
    buttons = [c for c in comps if c.get("component") == "Button"]
    has_form = any(c.get("component") == "Form" for c in comps)
    if rules.get("una_accion_primaria"):
        primaries = [b for b in buttons if b.get("variant") == "primary"]
        if len(primaries) + (1 if has_form else 0) > 1:
            out.append(_f("PRIMARY_MULTIPLE", Severity.MAJOR, "design", f"Hay {len(primaries) + has_form} acciones primarias; solo puede haber una"))
    for b in buttons:
        cmd = spec.commands.get((b.get("action") or {}).get("command", ""))
        destructive = bool(cmd and cmd.tipo == "eliminar")
        if destructive and view.patron not in rules["destructivo_solo_en"]:
            out.append(_f("DESTRUCTIVE_OUTSIDE_CONFIRM", Severity.BLOCKING, "design", f"«{b.get('label')}» elimina fuera de una pantalla de confirmación"))
        if b.get("variant") == "danger" and not destructive:
            out.append(_f("DANGER_NOT_DESTRUCTIVE", Severity.MAJOR, "design", f"«{b.get('label')}» usa danger sin eliminar nada"))
        if destructive and b.get("variant") != "danger":
            out.append(_f("DESTRUCTIVE_NOT_DANGER", Severity.MAJOR, "design", f"«{b.get('label')}» elimina y debe usar danger"))
    if has_form and view.patron not in rules["formulario_solo_en"]:
        out.append(_f("FORM_OUTSIDE", Severity.BLOCKING, "design", "Form solo se permite en pantallas de formulario"))
    if view.patron in rules["formulario_solo_en"] and sum(c.get("component") == "Form" for c in comps) != 1:
        out.append(_f("FORM_COUNT", Severity.BLOCKING, "design", "Una pantalla de formulario necesita exactamente un Form"))
    if view.patron in rules["destructivo_solo_en"]:
        if not any(spec.commands.get((b.get("action") or {}).get("command", "")) for b in buttons):
            out.append(_f("CONFIRM_NO_COMMAND", Severity.BLOCKING, "design", "La confirmación necesita un botón que ejecute el comando"))
    root = next((c for c in comps if c.get("id") == doc.get("root")), {})
    by_id = {c.get("id"): c for c in comps}
    for ref in root.get("children", []) or []:
        child = by_id.get(ref, {})
        if child.get("component") and child["component"] not in rules["raiz_permitidos"]:
            out.append(_f("ROOT_CHILD", Severity.MINOR, "design", f"{child['component']} directamente bajo Page; mejor dentro de una Card"))
    return out


def verify_screen(doc: Any, view: ViewSpec, spec: CompiledSpec, catalog: Catalog) -> tuple[dict[str, Any], list[Finding]]:
    """Ejecuta las capas en orden; si la estructura falla, no tiene sentido seguir."""
    doc, findings = normalize(doc)
    doc["view"] = view.id
    findings += verify_structure(doc, catalog)
    if any(f.severity == Severity.BLOCKING for f in findings):
        return doc, findings
    findings += verify_graph_and_bindings(doc, view, spec, catalog)
    findings += verify_design(doc, view, spec)
    return doc, findings
