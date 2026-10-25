"""Funciones de aptitud de la arquitectura (docs/04-puntos-de-control.md §6)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from conftest import APPS, REPO

from eidos.agents import composer_prompt, interpreter_prompt
from eidos.catalog import Catalog
from eidos.contracts import (
    AppManifest,
    ArtifactStatus,
    CommandSpec,
    EntitySpec,
    FieldSpec,
    MetricSpec,
    Requirement,
    RiskClass,
    Route,
    RuleSpec,
    Severity,
    ViewSpec,
    Voice,
)
from eidos.reconciler import admit_and_compile
from eidos.specs import load_yaml

PLATFORM_SRC = REPO / "platform" / "src" / "eidos"


def _contract_vocabulary() -> set[str]:
    """Vocabulario propio de la plataforma: claves de contrato, tipos, estados y clases. Que un dominio use la misma
    palabra («alta», «estado», «provisional») no implica que la plataforma sepa nada de ese dominio."""
    words: set[str] = set()
    for model in (AppManifest, Requirement, FieldSpec, EntitySpec, MetricSpec, RuleSpec, ViewSpec, CommandSpec, Voice):
        words |= {k.lower() for k in model.model_fields}
    for enum in (ArtifactStatus, RiskClass, Route, Severity):
        words |= {e.value for e in enum}
    # «user» es el rol del protocolo de chat de los proveedores de modelos.
    return words | {"texto", "email", "enum", "booleano", "fecha", "fechahora", "numero", "referencia", "estado", "capacidad", "user"}


def _domain_terms(apps_dir: Path) -> set[str]:
    terms: set[str] = set()
    for app in APPS:
        spec, _ = admit_and_compile(app)
        for e in spec.entities.values():
            terms |= {e.entidad, e.etiqueta, e.plural, *e.campos, *e.metricas}
            for f in e.campos.values():
                terms |= {v.valor for v in f.valores}
        terms |= set(spec.rules) | {v.split(".")[0] for v in spec.views} | {c.split(".")[0] for c in spec.commands}
    return {t.lower() for t in terms if len(t) >= 4} - _contract_vocabulary()


def test_F1_platform_has_no_domain_knowledge(isolated: Path) -> None:
    terms = _domain_terms(isolated)
    assert terms, "No se han extraído términos de dominio"
    hits = []
    for file in PLATFORM_SRC.rglob("*"):
        if file.suffix not in (".py", ".yaml", ".json"):
            continue
        text = file.read_text(encoding="utf-8").lower()
        for t in terms:
            if re.search(rf"\b{re.escape(t)}\b", text):
                hits.append(f"{file.relative_to(PLATFORM_SRC)}: «{t}»")
    assert not hits, "Conocimiento de dominio en la plataforma:\n" + "\n".join(hits)


def test_F2_witness_domain_builds_with_the_same_platform() -> None:
    from eidos.service import Platform
    report = Platform().reconciler().run("reservas")
    assert report["screens"] and all(s["blocking"] == 0 for s in report["screens"].values())


def test_F3_prompts_are_derived_from_specs(isolated: Path) -> None:
    spec, _ = admit_and_compile("usuarios")
    before = composer_prompt(spec, spec.views["user.list"], Catalog())
    file = isolated / "usuarios" / "tecnico" / "entidades" / "Usuario.yaml"
    data = load_yaml(file.read_text(encoding="utf-8"))
    data["campos"]["departamento"]["etiqueta"] = "Área de negocio"
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    spec2, _ = admit_and_compile("usuarios")
    after = composer_prompt(spec2, spec2.views["user.list"], Catalog())
    assert "Área de negocio" in after and "Área de negocio" not in before


def test_RP07_prompts_never_contain_real_records(isolated: Path) -> None:
    for app in APPS:
        spec, _ = admit_and_compile(app)
        values: set[str] = set()
        for f in (isolated / app / "datos" / "semillas").glob("*.json"):
            for row in json.loads(f.read_text(encoding="utf-8")):
                values |= {str(v) for k, v in row.items() if k != "id" and isinstance(v, str) and len(v) > 3}
        prompts = [composer_prompt(spec, v, Catalog()) for v in spec.views.values()]
        prompts.append(interpreter_prompt(spec, "hola", None))
        leaked = {v for v in values for p in prompts if v in p and v not in {x.valor for e in spec.entities.values() for f in e.campos.values() for x in f.valores}}
        assert not leaked, f"{app}: datos reales en prompts: {leaked}"
