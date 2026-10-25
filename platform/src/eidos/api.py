"""API HTTP: plano de ejecución (/api) y plano de control (/control)."""
from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .config import settings
from .contracts import Route
from .llm import LLMError, profiles
from .reconciler import BuildError, list_apps
from .service import Platform


def create_app(platform: Platform | None = None) -> FastAPI:
    pf = platform or Platform()
    app = FastAPI(title="Eidos", version=__version__)

    @app.middleware("http")
    async def json_only(request: Request, call_next):
        # Exigir JSON en escrituras fuerza preflight CORS: otra web no puede lanzar acciones aquí.
        if request.method not in ("GET", "HEAD") and request.url.path.startswith(("/api/", "/control/")):
            if not request.headers.get("content-type", "").startswith("application/json"):
                return JSONResponse({"error": "Usa Content-Type: application/json"}, status_code=415)
        return await call_next(request)

    def service(app_id: str):
        try:
            return pf.app(app_id)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        except BuildError as e:
            raise HTTPException(422, {"stage": e.stage, "findings": [f.model_dump(mode="json") for f in e.findings]}) from e

    # ------------------------------------------------------------ plano de ejecución
    @app.get("/api/apps")
    def apps() -> list[str]:
        return list_apps()

    @app.get("/api/apps/{app_id}")
    def manifest(app_id: str) -> dict[str, Any]:
        return service(app_id).manifest()

    @app.post("/api/apps/{app_id}/views/{view_id}")
    def view(app_id: str, view_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        try:
            return service(app_id).view(view_id, body.get("params") or {})
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except LookupError as e:
            raise HTTPException(410, str(e)) from e

    @app.post("/api/apps/{app_id}/commands/{command_id}")
    def command(app_id: str, command_id: str, body: dict[str, Any] = Body(default={})) -> JSONResponse:
        result = service(app_id).command(command_id, body.get("input") or {})
        return JSONResponse(result, status_code=200 if result.get("ok") else 422)

    @app.post("/api/apps/{app_id}/ask")
    def ask(app_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        try:
            return service(app_id).ask(str(body.get("text", ""))[:1000], body.get("current"))
        except LLMError as e:
            return {"reply": "El asistente no está disponible ahora mismo.", "view": None, "error": str(e)}

    # ------------------------------------------------------------ plano de control
    @app.get("/control/profiles")
    def list_profiles() -> dict[str, Any]:
        try:
            active = pf.profile.id
        except LLMError:
            active = None
        return {"active": active, "profiles": [p.public() for p in profiles().values()]}

    @app.put("/control/profiles")
    def set_profile(body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        try:
            pf.set_profile(str(body.get("profile", "")))
        except LLMError as e:
            raise HTTPException(400, str(e)) from e
        return list_profiles()

    @app.post("/control/profiles/{profile_id}/test")
    def test_profile(profile_id: str) -> dict[str, Any]:
        return pf.test_profile(profile_id)

    @app.get("/control/apps")
    def apps_summary() -> list[dict[str, Any]]:
        return pf.apps_summary()

    @app.post("/control/apps/{app_id}/build")
    def build(app_id: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        service(app_id)
        try:
            return pf.reconciler().run(app_id, Route(body.get("mode", "lote")), actor="consola")
        except BuildError as e:
            raise HTTPException(422, {"stage": e.stage, "findings": [f.model_dump(mode="json") for f in e.findings]}) from e
        except LLMError as e:
            raise HTTPException(502, str(e)) from e

    @app.get("/control/apps/{app_id}/artifacts")
    def artifacts(app_id: str) -> list[dict[str, Any]]:
        return service(app_id).artifacts()

    @app.get("/control/apps/{app_id}/artifacts/{kind}/{key}")
    def history(app_id: str, kind: str, key: str) -> list[dict[str, Any]]:
        return service(app_id).history(kind, key)

    @app.post("/control/apps/{app_id}/screens/{key}/regenerate")
    def regenerate(app_id: str, key: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        motive = str(body.get("motivo", "")).strip()
        if not motive:
            raise HTTPException(400, "Regenerar exige un motivo")
        try:
            return service(app_id).regenerate(key, motive)
        except KeyError as e:
            raise HTTPException(404, str(e)) from e
        except LLMError as e:
            raise HTTPException(502, str(e)) from e

    @app.get("/control/apps/{app_id}/report")
    def report(app_id: str) -> dict[str, Any]:
        return service(app_id).latest_report() or {}

    @app.post("/control/apps/{app_id}/screens/{key}/preview")
    def preview(app_id: str, key: str, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        try:
            return service(app_id).preview(key, body.get("revision"))
        except LookupError as e:
            raise HTTPException(404, str(e)) from e

    @app.get("/control/interventions")
    def interventions(app: str | None = None, status: str | None = "abierta") -> list[dict[str, Any]]:
        return [i.model_dump(mode="json") for i in pf.store.interventions(app, status)]

    @app.post("/control/interventions/{iid}")
    def resolve(iid: int, body: dict[str, Any] = Body(default={})) -> dict[str, Any]:
        try:
            return pf.reconciler().resolve(iid, body.get("decision") == "aprobar", str(body.get("motivo", "")), actor="consola")
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

    @app.get("/control/apps/{app_id}/audit")
    def audit(app_id: str) -> list[dict[str, Any]]:
        return pf.store.audit_log(app_id)

    client = settings().client_dir
    if client.is_dir():
        app.mount("/", StaticFiles(directory=client, html=True), name="client")
    return app
