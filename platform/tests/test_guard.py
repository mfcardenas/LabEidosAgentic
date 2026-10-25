from __future__ import annotations

from typing import Any

from eidos.catalog import Catalog
from eidos.contracts import Severity
from eidos.guard import verify_screen
from eidos.patterns import fallback
from eidos.reconciler import admit_and_compile


def _check(doc: Any, view_id: str = "user.list") -> set[str]:
    spec, _ = admit_and_compile("usuarios")
    _, findings = verify_screen(doc, spec.views[view_id], spec, Catalog())
    return {f.code for f in findings if f.severity in (Severity.BLOCKING, Severity.MAJOR)}


def _base(view_id: str = "user.list") -> dict[str, Any]:
    spec, _ = admit_and_compile("usuarios")
    return fallback(spec, spec.views[view_id])


def test_unknown_component_is_blocking() -> None:
    doc = _base()
    doc["components"].append({"id": "chart", "component": "Chart"})
    assert "COMPONENT_UNKNOWN" in _check(doc)


def test_unknown_binding_path_is_blocking() -> None:
    doc = _base("user.detail")
    kv = next(c for c in doc["components"] if c["component"] == "KeyValue")
    kv["items"].append({"label": "Teléfono", "value": {"path": "/item/telefono"}})
    assert "BINDING_UNKNOWN_PATH" in _check(doc, "user.detail")


def test_missing_child_reference_is_blocking() -> None:
    doc = _base()
    doc["components"][0]["children"].append("ghost")
    assert "REF_MISSING" in _check(doc)


def test_destructive_action_outside_confirmation_is_blocking() -> None:
    doc = _base("user.detail")
    doc["components"].append({"id": "kill", "component": "Button", "label": "Borrar", "variant": "danger",
                              "action": {"command": "usuario.eliminar", "input": {"id": {"path": "/item/id"}}}})
    doc["components"][0]["actions"].append("kill")
    assert "DESTRUCTIVE_OUTSIDE_CONFIRM" in _check(doc, "user.detail")


def test_two_primary_actions_is_major() -> None:
    doc = _base()
    doc["components"].append({"id": "other", "component": "Button", "label": "Otra", "variant": "primary",
                              "action": {"function": "navigate", "args": {"view": "user.list"}}})
    doc["components"][0]["actions"].append("other")
    assert "PRIMARY_MULTIPLE" in _check(doc)


def test_form_missing_required_field_is_blocking() -> None:
    doc = _base("user.create")
    form = next(c for c in doc["components"] if c["component"] == "Form")
    form["fields"] = [f for f in form["fields"] if f["field"] != "email"]
    assert "FORM_REQUIRED_MISSING" in _check(doc, "user.create")


def test_normalize_fixes_common_model_mistakes() -> None:
    doc = _base()
    table = next(c for c in doc["components"] if c["component"] == "Table")
    table["rows"] = '{"path": "/items"}'
    stat = next(c for c in doc["components"] if c["component"] == "Stat")
    stat["props"] = {"hint": "todas"}
    assert not _check(doc)
