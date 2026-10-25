"""Pruebas de conformidad declarativas sobre documentos de pantalla (oráculo determinista, sin navegador).

Las pruebas son entradas humanas (pruebas/conformidad/*.yaml); el sistema las ejecuta pero no las modifica (RP-03).
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..contracts import CompiledSpec, ConformanceTest, Finding, Severity

Doc = dict[str, Any]


def _comps(doc: Doc) -> list[dict[str, Any]]:
    return [c for c in doc.get("components", []) if isinstance(c, dict)]


def _nav_target(c: dict[str, Any]) -> str | None:
    a = c.get("action") or {}
    return (a.get("args") or {}).get("view") if a.get("function") == "navigate" else None


def _header_actions(doc: Doc) -> list[dict[str, Any]]:
    by_id = {c.get("id"): c for c in _comps(doc)}
    root = by_id.get(doc.get("root"), {})
    return [by_id[i] for i in root.get("actions", []) or [] if i in by_id]


def a_tiene_accion_primaria(doc: Doc, spec: CompiledSpec, arg: dict[str, Any]) -> str | None:
    prim = [c for c in _comps(doc) if c.get("component") == "Button" and c.get("variant") == "primary"]
    if not prim:
        return "no hay acción primaria"
    target = arg.get("vista_destino") if isinstance(arg, dict) else None
    if target and not any(_nav_target(c) == target for c in prim):
        return f"la acción primaria no navega a {target}"
    return None


def a_tiene_componente(doc: Doc, spec: CompiledSpec, arg: dict[str, Any]) -> str | None:
    cands = [c for c in _comps(doc) if c.get("component") == arg["tipo"]]
    if not cands:
        return f"no hay ningún {arg['tipo']}"
    if want := arg.get("columnas_incluyen"):
        if not any(set(want) <= {col.get("field") for col in c.get("columns", [])} for c in cands):
            return f"ninguna {arg['tipo']} incluye las columnas {', '.join(want)}"
    if want := arg.get("campos_incluyen"):
        if not any(set(want) <= {f.get("field") for f in c.get("fields", [])} for c in cands):
            return f"ningún {arg['tipo']} incluye los campos {', '.join(want)}"
    if want := arg.get("comando"):
        if not any(c.get("command") == want or (c.get("action") or {}).get("command") == want for c in cands):
            return f"ningún {arg['tipo']} ejecuta {want}"
    return None


def a_no_tiene_componente(doc: Doc, spec: CompiledSpec, arg: dict[str, Any]) -> str | None:
    return f"no debería haber {arg['tipo']}" if any(c.get("component") == arg["tipo"] for c in _comps(doc)) else None


def a_tiene_accion(doc: Doc, spec: CompiledSpec, arg: dict[str, Any]) -> str | None:
    buttons = [c for c in _comps(doc) if c.get("component") == "Button"]
    if arg.get("en_cabecera"):
        buttons = [c for c in _header_actions(doc) if c.get("component") == "Button"]
    for b in buttons:
        a = b.get("action") or {}
        if "comando" in arg and a.get("command") != arg["comando"]:
            continue
        if "vista_destino" in arg and _nav_target(b) != arg["vista_destino"]:
            continue
        if "variante" in arg and b.get("variant") != arg["variante"]:
            continue
        return None
    return f"no hay ninguna acción que cumpla {arg}"


def a_no_tiene_accion(doc: Doc, spec: CompiledSpec, arg: dict[str, Any]) -> str | None:
    for b in (c for c in _comps(doc) if c.get("component") == "Button"):
        cmd = spec.commands.get((b.get("action") or {}).get("command", ""))
        if cmd and arg.get("comando_tipo") == cmd.tipo:
            return f"«{b.get('label')}» ejecuta un comando de tipo {cmd.tipo}"
    return None


def a_max_nodos(doc: Doc, spec: CompiledSpec, arg: Any) -> str | None:
    n = len(_comps(doc))
    return f"{n} componentes (máximo {arg})" if n > int(arg) else None


def a_titulo_enlazado(doc: Doc, spec: CompiledSpec, arg: dict[str, Any]) -> str | None:
    root = next((c for c in _comps(doc) if c.get("id") == doc.get("root")), {})
    title = root.get("title")
    return None if isinstance(title, dict) and title.get("path") == arg["path"] else f"el título no enlaza {arg['path']}"


ASSERTIONS: dict[str, Callable[[Doc, CompiledSpec, Any], str | None]] = {
    "tiene_accion_primaria": a_tiene_accion_primaria,
    "tiene_componente": a_tiene_componente,
    "no_tiene_componente": a_no_tiene_componente,
    "tiene_accion": a_tiene_accion,
    "no_tiene_accion": a_no_tiene_accion,
    "max_nodos": a_max_nodos,
    "titulo_enlazado": a_titulo_enlazado,
}


def run_conformance(doc: Doc, view_id: str, spec: CompiledSpec) -> list[Finding]:
    out: list[Finding] = []
    tests: list[ConformanceTest] = [t for t in spec.tests if t.vista == view_id]
    for t in tests:
        for i, assertion in enumerate(t.aserciones):
            ((name, arg),) = assertion.items()
            fn = ASSERTIONS.get(name)
            if not fn:
                out.append(Finding(code="TEST_UNKNOWN_ASSERTION", severity=Severity.BLOCKING, layer="tests", source="test:conformance",
                                   message=f"Aserción desconocida «{name}» (opciones: {', '.join(ASSERTIONS)})", path=f"{t.fichero}#{i}"))
                continue
            if (msg := fn(doc, spec, arg or {})):
                out.append(Finding(code=f"TEST_{name.upper()}", severity=Severity.BLOCKING, layer="tests", source="test:conformance",
                                   message=f"{t.fichero}: {msg}", path=f"{t.fichero}#{i}"))
    return out
