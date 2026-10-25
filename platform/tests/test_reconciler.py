from __future__ import annotations

from pathlib import Path

import yaml

from eidos.contracts import ArtifactStatus, Route
from eidos.service import Platform
from eidos.specs import load_yaml


def _approve_all(pf: Platform, app: str) -> None:
    for it in pf.store.interventions(app, "abierta"):
        if it.type.value in ("H1", "H4"):
            pf.reconciler().resolve(it.id, True, "", actor="prueba")


def test_batch_build_pilot_end_to_end() -> None:
    pf = Platform()
    report = pf.reconciler().run("usuarios")
    assert report["spec_status"] == "pendiente_aprobacion"
    assert {i["type"] for i in report["interventions"]} == {"H1"}
    assert all(s["status"] == "candidato" for s in report["screens"].values())

    _approve_all(pf, "usuarios")  # H1 → se promocionan candidatos; la clase alta abre H4
    statuses = {r.key: r.status for r in pf.store.current("usuarios", "screen")}
    assert statuses["user.list"] == ArtifactStatus.PUBLISHED
    assert statuses["user.delete"] == ArtifactStatus.PENDING_APPROVAL
    assert statuses["user.edit"] == ArtifactStatus.PENDING_APPROVAL  # regla crítica → clase alta

    _approve_all(pf, "usuarios")
    assert all(r.status == ArtifactStatus.PUBLISHED for r in pf.store.current("usuarios", "screen"))


def test_reconciliation_is_idempotent() -> None:
    pf = Platform()
    pf.reconciler().run("reservas")
    _approve_all(pf, "reservas")
    _approve_all(pf, "reservas")
    again = pf.reconciler().run("reservas")
    assert again["changes"] == []


def test_dependency_change_revalidates_only_affected_screens(isolated: Path) -> None:
    pf = Platform()
    pf.reconciler().run("reservas")
    _approve_all(pf, "reservas")
    _approve_all(pf, "reservas")
    file = isolated / "reservas" / "tecnico" / "entidades" / "Sala.yaml"
    data = load_yaml(file.read_text(encoding="utf-8"))
    data["campos"]["capacidad"]["etiqueta"] = "Aforo"
    file.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    report = pf.reconciler().run("reservas")
    touched = {c["key"] for c in report["changes"] if c["kind"] == "screen"}
    assert touched and all(k.startswith("sala.") or k.startswith("reserva.") for k in touched)
    assert "reserva.list" not in touched or "entity:Sala" in pf.store.latest("reservas", "screen", "reserva.list").fingerprints
    assert {c["action"] for c in report["changes"] if c["kind"] == "screen"} <= {"revalidate"}


def test_on_demand_only_builds_low_risk_views() -> None:
    pf = Platform()
    report = pf.reconciler().run("usuarios", Route.ON_DEMAND, {"user.list", "user.delete"})
    keys = {c["key"]: c["status"] for c in report["changes"]}
    assert keys == {"user.list": "provisional"}


def test_runtime_serves_fallback_until_published() -> None:
    pf = Platform()
    out = pf.app("usuarios").view("user.edit", {"id": "u01"})
    assert out["source"] == "fallback" and out["data"]["item"]["nombre"] == "Lucía Ferrer"
    out = pf.app("usuarios").view("user.list", {})
    assert out["source"] == "on_demand" and out["data"]["count"] == 8
