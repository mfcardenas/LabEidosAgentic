from __future__ import annotations

from eidos.service import Platform


def test_unique_email_and_required_fields() -> None:
    app = Platform().app("usuarios")
    r = app.command("usuario.crear", {"nombre": "Ana", "email": "LUCIA.FERRER@ejemplo.com"})
    assert not r["ok"] and "email" in r["errors"]
    r = app.command("usuario.crear", {"nombre": "", "email": "x@y.es"})
    assert not r["ok"] and "nombre" in r["errors"]
    r = app.command("usuario.crear", {"nombre": "Marta Pons", "email": "marta@ejemplo.com", "rol": "Editora"})
    assert r["ok"] and r["record"]["rol"] == "editor" and r["record"]["alta"] and r["next"]["view"] == "user.detail"


def test_last_active_admin_rule() -> None:
    app = Platform().app("usuarios")
    assert app.command("usuario.actualizar", {"id": "u01", "activo": False})["ok"]
    r = app.command("usuario.actualizar", {"id": "u06", "rol": "lector"})
    assert not r["ok"] and "administrador" in r["errors"]["_"]
    r = app.command("usuario.eliminar", {"id": "u06"})
    assert not r["ok"]


def test_no_overlapping_confirmed_bookings() -> None:
    app = Platform().app("reservas")
    base = {"titulo": "Reunión", "sala": "s01", "responsable": "a@b.es", "estado": "confirmada"}
    r = app.command("reserva.crear", base | {"inicio": "2026-10-27T10:00", "fin": "2026-10-27T10:30"})
    assert not r["ok"] and "solapa" in r["errors"]["_"]
    r = app.command("reserva.crear", base | {"inicio": "2026-10-27T11:00", "fin": "2026-10-27T10:00"})
    assert not r["ok"] and "fin" in r["errors"]
    r = app.command("reserva.crear", base | {"estado": "provisional", "inicio": "2026-10-27T10:00", "fin": "2026-10-27T10:30"})
    assert r["ok"]
    assert app.command("reserva.eliminar", {"id": r["record"]["id"]})["ok"]


def test_view_models_resolve_references_and_filters() -> None:
    app = Platform().app("reservas")
    data = app.data().view_model(app.spec.views["reserva.list"], {"filtro": {"sala": "Atlántico"}})
    assert data["count"] == 2 and all(i["sala_titulo"] == "Atlántico" for i in data["items"])
    assert data["filter"]["label"] == "Sala: Atlántico"
    form = app.data().view_model(app.spec.views["reserva.create"], {})
    assert {o["label"] for o in form["options"]["sala"]} >= {"Atlántico", "Mediterráneo"}


def test_interpreter_resolves_records_without_sending_data() -> None:
    app = Platform().app("usuarios")
    out = app.ask("busca a Lucía", None)
    assert out["view"] == "user.list" and out["params"]["filtro"] == {"q": "busca a Lucía"}
