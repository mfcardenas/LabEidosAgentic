"""Servicio de aplicación: une especificación publicada, artefactos, datos y agentes para el plano de ejecución."""
from __future__ import annotations

import json
from collections import Counter
from functools import cached_property
from typing import Any

from .agents import interpret
from .catalog import Catalog
from .config import settings
from .contracts import ArtifactStatus, CompiledSpec, Route, Severity
from .guard import verify_screen
from .llm import LLMError, Profile, complete_json, get_profile
from .patterns import fallback
from .policy import classify
from .reconciler import Reconciler, admit_and_compile, app_dir, list_apps
from .runtime import Commands, Data, Repository
from .specs import load_bundle
from .store import Store


class Platform:
    """Punto de entrada único para la API y la CLI."""

    def __init__(self, profile: Profile | None = None):
        s = settings()
        self.store = Store(s.data_dir / "artifacts.db")
        self.catalog = Catalog()
        self._profile = profile
        self._apps: dict[str, AppService] = {}

    @property
    def profile(self) -> Profile:
        """Perfil explícito, el elegido en la consola (persistido) o el de EIDOS_PROFILE, en ese orden."""
        if self._profile:
            return self._profile
        stored = self.store.get_setting("profile")
        if stored:
            try:
                return get_profile(stored)
            except LLMError:
                pass
        return get_profile()

    def set_profile(self, profile_id: str, actor: str = "consola") -> Profile:
        p = get_profile(profile_id)
        self.store.set_setting("profile", p.id)
        self.store.audit("*", actor, "perfil", {"profile": p.id})
        return p

    def test_profile(self, profile_id: str) -> dict[str, Any]:
        try:
            p = get_profile(profile_id)
            _, meta = complete_json(p, "composer", 'Responde SOLO con este JSON: {"ok": true}', fake=lambda: {"ok": True})
            return {"ok": True, "seconds": meta.get("seconds"), "model": meta.get("model")}
        except LLMError as e:
            return {"ok": False, "error": str(e)}

    def apps_summary(self) -> list[dict[str, Any]]:
        out = []
        for app in list_apps():
            arts = self.store.current(app)
            spec = next((a for a in arts if a.kind == "spec"), None)
            out.append({
                "app": app,
                "spec": {"status": spec.status.value, "version": spec.document.get("version")} if spec else None,
                "screens": dict(Counter(a.status.value for a in arts if a.kind == "screen")),
                "interventions": len(self.store.interventions(app, "abierta")),
            })
        return out

    def reconciler(self) -> Reconciler:
        return Reconciler(self.store, self.catalog, self.profile)

    def app(self, app_id: str) -> AppService:
        if app_id not in self._apps:
            app_dir(app_id)
            self._apps[app_id] = AppService(self, app_id)
        return self._apps[app_id]


class AppService:
    def __init__(self, platform: Platform, app_id: str):
        self.platform, self.id = platform, app_id

    @property
    def spec(self) -> CompiledSpec:
        """La especificación publicada manda; sin publicar, se usa la compilada de las entradas (laboratorio)."""
        rec = self.platform.store.published(self.id, "spec", "spec")
        return CompiledSpec.model_validate(rec.document) if rec else admit_and_compile(self.id)[0]

    @property
    def spec_published(self) -> bool:
        return self.platform.store.published(self.id, "spec", "spec") is not None

    @cached_property
    def repo(self) -> Repository:
        repo = Repository(settings().data_dir / "apps" / f"{self.id}.db")
        bundle, _ = load_bundle(app_dir(self.id))
        if bundle:
            Data(self.spec, repo).seed(bundle.seeds)
        return repo

    def data(self) -> Data:
        return Data(self.spec, self.repo)

    def manifest(self) -> dict[str, Any]:
        spec = self.spec
        return {
            "app": spec.app.model_dump(), "version": spec.version, "published": self.spec_published, "tokens": spec.tokens,
            "views": {k: {"titulo": v.titulo, "patron": v.patron, "entidad": v.entidad, "parametros": v.parametros.model_dump()} for k, v in spec.views.items()},
            "entities": {k: e.model_dump() for k, e in spec.entities.items()},
            "commands": {k: {"tipo": c.tipo, "entidad": c.entidad, "etiqueta": c.etiqueta} for k, c in spec.commands.items()},
            "catalog": self.platform.catalog.fingerprint,
        }

    def view(self, view_id: str, params: dict[str, Any]) -> dict[str, Any]:
        spec = self.spec
        view = spec.views.get(view_id)
        if not view:
            raise KeyError(f"La vista «{view_id}» no existe")
        trace: list[dict[str, Any]] = []
        data = self.data().view_model(view, params)
        trace.append({"step": "datos", "text": f"Modelo de datos de {view_id} ({view.patron})"})
        store = self.platform.store
        decision = classify(view, spec)
        rec = store.published(self.id, "screen", view_id) or store.with_status(self.id, "screen", view_id, ArtifactStatus.PROVISIONAL)
        source = "published" if rec and rec.status == ArtifactStatus.PUBLISHED else "provisional" if rec else None
        trace.append({"step": "artefacto", "text": f"{rec.ref} ({rec.status.value})" if rec else "Sin artefacto publicado",
                      "risk": decision.risk.value, "route": decision.route.value})
        if rec is None and decision.route == Route.ON_DEMAND:
            try:
                report = self.platform.reconciler().run(self.id, Route.ON_DEMAND, {view_id}, actor="demanda")
                rec = store.with_status(self.id, "screen", view_id, ArtifactStatus.PROVISIONAL, ArtifactStatus.PUBLISHED)
                source = "on_demand" if rec else None
                for c in report["changes"]:
                    trace.append({"step": "demanda", "text": f"{c['action']} → {c['status']} · {c['attempts']} intento(s)", "findings": c["findings"],
                                  "profile": report["profile"]})
            except LLMError as e:
                trace.append({"step": "demanda", "text": f"Sin modelo: {e}", "status": "fail"})
                rec = None
        if rec is None:
            # Plantilla de respaldo del patrón: determinista y verificada igualmente (RP-01).
            doc, findings = verify_screen(fallback(spec, view), view, spec, self.platform.catalog)
            if any(f.severity == Severity.BLOCKING for f in findings):
                raise RuntimeError(f"La plantilla de respaldo de {view_id} no es válida")
            trace.append({"step": "respaldo", "text": f"Plantilla de respaldo del patrón {view.patron}, verificada"})
            return {"view": view_id, "params": params, "document": doc, "data": data, "source": "fallback", "artifact": None, "trace": trace}
        return {"view": view_id, "params": params, "document": rec.document, "data": data, "source": source, "artifact": rec.ref, "trace": trace}

    # ------------------------------------------------------------ plano de control de la aplicación
    def preview_params(self, view_id: str) -> dict[str, Any]:
        view = self.spec.views[view_id]
        if not view.parametros.id:
            return {}
        rows = self.data().all(self.spec.entities[view.entidad])
        return {"id": rows[0]["id"]} if rows else {}

    def artifacts(self) -> list[dict[str, Any]]:
        views = self.spec.views
        out = []
        for r in self.platform.store.current(self.id):
            d = r.model_dump(mode="json") | {"ref": r.ref}
            if r.kind == "screen" and r.key in views:
                d["preview"] = self.preview_params(r.key)
                d["title"] = views[r.key].titulo
            out.append(d)
        return out

    def history(self, kind: str, key: str) -> list[dict[str, Any]]:
        return [r.model_dump(mode="json") | {"ref": r.ref} for r in self.platform.store.history(self.id, kind, key)]

    def preview(self, view_id: str, revision: int | None = None) -> dict[str, Any]:
        """Cualquier revisión (también candidatas pendientes de aprobar) con datos reales, para revisarla antes de publicar."""
        hist = self.platform.store.history(self.id, "screen", view_id)
        rec = next((r for r in hist if r.revision == revision), None) if revision else (hist[-1] if hist else None)
        if rec is None or not rec.document.get("components") or view_id not in self.spec.views:
            raise LookupError("Esa revisión no tiene documento que mostrar")
        params = self.preview_params(view_id)
        data = self.data().view_model(self.spec.views[view_id], params)
        return {"view": view_id, "params": params, "document": rec.document, "data": data, "artifact": rec.ref, "status": rec.status.value}

    def regenerate(self, view_id: str, motive: str, actor: str = "consola") -> dict[str, Any]:
        if view_id not in self.spec.views:
            raise KeyError(f"La vista «{view_id}» no existe")
        self.platform.store.audit(self.id, actor, "regenerar", {"screen": view_id, "motive": motive})
        return self.platform.reconciler().run(self.id, Route.BATCH, {view_id}, actor=actor, force={view_id})

    def latest_report(self) -> dict[str, Any] | None:
        folder = settings().data_dir / "reports" / self.id
        files = sorted(folder.glob("*.json")) if folder.is_dir() else []
        return json.loads(files[-1].read_text(encoding="utf-8")) if files else None

    def command(self, command_id: str, input: dict[str, Any]) -> dict[str, Any]:
        result = Commands(self.data()).execute(command_id, input)
        if result.get("ok"):
            self.platform.store.audit(self.id, "persona", f"comando:{command_id}", {"id": result["record"].get("id")})
        return result

    def ask(self, text: str, current: dict[str, Any] | None) -> dict[str, Any]:
        spec = self.spec
        value, meta = interpret(spec, text, current, self.platform.profile)
        view_id = value.get("view")
        if view_id not in spec.views:
            return {"reply": value.get("reply") or "Eso no lo puedo resolver aquí.", "view": None, "meta": meta}
        view = spec.views[view_id]
        raw = value.get("params") or {}
        params: dict[str, Any] = {}
        data = self.data()
        e = spec.entities[view.entidad]
        if view.parametros.filtro and raw.get("filtro"):
            params["filtro"] = data.normalize_filter(e, raw["filtro"])
        if view.parametros.prefill and raw.get("prefill"):
            params["prefill"] = data.clean_input(e, raw["prefill"], partial=True)[0]
        if view.parametros.id:
            text_ref = (value.get("search") or {}).get("text") or ""
            hits = [r for name, r in data.search(text_ref) if name == view.entidad] if text_ref else []
            if len(hits) != 1:
                return {"reply": f"No encuentro un único {e.etiqueta} con «{text_ref}»." if text_ref else f"¿Qué {e.etiqueta}?", "view": None, "meta": meta}
            params["id"] = hits[0]["id"]
        return {"reply": value.get("reply") or "", "view": view_id, "params": params, "meta": meta}
