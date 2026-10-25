from __future__ import annotations

from fastapi.testclient import TestClient

from eidos.api import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_writes_require_json_content_type() -> None:
    c = _client()
    r = c.post("/api/apps/usuarios/commands/usuario.crear", content="x", headers={"Content-Type": "text/plain"})
    assert r.status_code == 415


def test_runtime_view_and_command() -> None:
    c = _client()
    r = c.post("/api/apps/usuarios/views/user.detail", json={"params": {"id": "u01"}})
    assert r.status_code == 200 and r.json()["source"] == "on_demand" and r.json()["trace"]
    r = c.post("/api/apps/usuarios/views/user.edit", json={"params": {"id": "u01"}})
    assert r.json()["source"] == "fallback"
    r = c.post("/api/apps/usuarios/commands/usuario.crear", json={"input": {"nombre": "X"}})
    assert r.status_code == 422 and "email" in r.json()["errors"]


def test_console_flow_build_approve_preview_regenerate() -> None:
    c = _client()
    assert c.put("/control/profiles", json={"profile": "fake"}).json()["active"] == "fake"
    assert c.put("/control/profiles", json={"profile": "nope"}).status_code == 400
    assert c.post("/control/apps/reservas/build", json={"mode": "lote"}).status_code == 200
    open_ = c.get("/control/interventions?app=reservas").json()
    assert [i["type"] for i in open_] == ["H1"]
    assert c.post(f"/control/interventions/{open_[0]['id']}", json={"decision": "rechazar"}).status_code == 400  # sin motivo
    assert c.post(f"/control/interventions/{open_[0]['id']}", json={"decision": "aprobar"}).json()["status"] == "publicado"
    arts = {a["key"]: a for a in c.get("/control/apps/reservas/artifacts").json() if a["kind"] == "screen"}
    assert arts["reserva.delete"]["status"] == "pendiente_aprobacion" and arts["reserva.detail"]["preview"] == {"id": "r01"}
    prev = c.post("/control/apps/reservas/screens/reserva.delete/preview", json={}).json()
    assert prev["status"] == "pendiente_aprobacion" and prev["data"]["item"]["id"] == "r01"
    assert c.post("/control/apps/reservas/screens/sala.list/regenerate", json={}).status_code == 400
    regen = c.post("/control/apps/reservas/screens/sala.list/regenerate", json={"motivo": "probar"}).json()
    assert [ch["key"] for ch in regen["changes"] if ch["kind"] == "screen"] == ["sala.list"]
    hist = c.get("/control/apps/reservas/artifacts/screen/sala.list").json()
    assert [h["status"] for h in hist] == ["desactualizado", "publicado"]
    assert c.get("/control/apps/reservas/report").json()["traceability"]
    assert any(a["action"] == "regenerar" for a in c.get("/control/apps/reservas/audit").json())
