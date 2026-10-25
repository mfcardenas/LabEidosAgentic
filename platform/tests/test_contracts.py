from __future__ import annotations

import pytest
from conftest import APPS, REPO
from jsonschema import Draft202012Validator

from eidos.catalog import Catalog
from eidos.contracts import Severity
from eidos.guard import verify_screen
from eidos.guard.conformance import run_conformance
from eidos.patterns import fallback
from eidos.reconciler import admit_and_compile


@pytest.mark.parametrize("app", APPS)
def test_inputs_admit_and_compile(app: str) -> None:
    spec, findings = admit_and_compile(app)
    assert not [f for f in findings if f.severity == Severity.BLOCKING]
    assert spec.version and spec.views and spec.requirements
    for req in spec.requirements:
        assert req.implementedBy, f"{req.id} sin implementación"
        assert req.testedBy, f"{req.id} sin pruebas"


@pytest.mark.parametrize("app", APPS)
def test_compilation_is_deterministic(app: str) -> None:
    assert admit_and_compile(app)[0].version == admit_and_compile(app)[0].version


def test_catalog_schema_is_valid_and_complete() -> None:
    cat = Catalog()
    Draft202012Validator.check_schema(cat.screen_schema())
    prompt = cat.prompt()
    for name in cat.components:
        assert f"- {name}:" in prompt


def test_every_component_has_a_client_implementation() -> None:
    """F8 (parcial): cada componente del catálogo tiene implementación registrada en el renderizador."""
    registry = (REPO / "client" / "src" / "components.ts").read_text(encoding="utf-8")
    for name in Catalog().components:
        assert f"  {name}:" in registry, f"Falta {name} en client/src/components.ts"


@pytest.mark.parametrize("app", APPS)
def test_fallback_templates_pass_every_gate(app: str) -> None:
    """La plantilla de respaldo es la red de seguridad: debe pasar guardián y pruebas sin hallazgos bloqueantes ni mayores."""
    spec, _ = admit_and_compile(app)
    cat = Catalog()
    for view in spec.views.values():
        doc, findings = verify_screen(fallback(spec, view), view, spec, cat)
        findings += run_conformance(doc, view.id, spec)
        bad = [f for f in findings if f.severity in (Severity.BLOCKING, Severity.MAJOR)]
        assert not bad, f"{app}/{view.id}: {[f.message for f in bad]}"
