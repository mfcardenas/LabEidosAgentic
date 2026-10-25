"""Reconciliador: compara el estado deseado (entradas) con el real (artefactos) y actúa sobre la diferencia (ADR-03).

observar → comparar → planificar → actuar (generar/reparar) → verificar → proponer o publicar → registrar
"""
from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .catalog import Catalog
from .config import settings
from .contracts import ArtifactStatus, CompiledSpec, Finding, Route, Severity, now_iso
from .kinds import KINDS, BuildContext, ScreenKind, SpecKind, publish
from .llm import Profile, get_profile
from .specs import compile_spec, load_bundle
from .store import Store


class BuildError(Exception):
    def __init__(self, stage: str, findings: list[Finding]):
        super().__init__(f"{stage}: {len(findings)} hallazgo(s) bloqueante(s)")
        self.stage, self.findings = stage, findings


def app_dir(app: str) -> Path:
    d = settings().apps_dir / app
    if not (d / "eidos.yaml").is_file():
        raise FileNotFoundError(f"No existe la aplicación «{app}» en {settings().apps_dir}")
    return d


def list_apps() -> list[str]:
    root = settings().apps_dir
    return sorted(p.name for p in root.iterdir() if (p / "eidos.yaml").is_file()) if root.is_dir() else []


def admit_and_compile(app: str) -> tuple[CompiledSpec, list[Finding]]:
    """G0 + G1. Lanza BuildError si hay hallazgos bloqueantes."""
    bundle, f0 = load_bundle(app_dir(app))
    if bundle is None or any(f.severity == Severity.BLOCKING for f in f0):
        raise BuildError("G0", f0)
    spec, f1 = compile_spec(bundle)
    if spec is None:
        raise BuildError("G1", f1)
    return spec, f0 + f1


class Reconciler:
    def __init__(self, store: Store, catalog: Catalog | None = None, profile: Profile | None = None):
        self.store = store
        self.catalog = catalog or Catalog()
        self.profile = profile or get_profile()

    def context(self, app: str, spec: CompiledSpec, mode: Route = Route.BATCH, keys: set[str] | None = None,
                force: set[str] | None = None) -> BuildContext:
        return BuildContext(app=app, spec=spec, catalog=self.catalog, store=self.store, profile=self.profile, mode=mode, keys=keys,
                            force=force or set())

    def run(self, app: str, mode: Route = Route.BATCH, keys: set[str] | None = None, actor: str = "sistema",
            force: set[str] | None = None) -> dict[str, Any]:
        started = now_iso()
        spec, admission = admit_and_compile(app)
        ctx = self.context(app, spec, mode, keys, force)
        items: list[dict[str, Any]] = []
        kinds = [k for k in KINDS if mode == Route.BATCH or k.name != "spec"]
        for kind in kinds:
            for change in kind.plan(ctx):
                rec = kind.build(ctx, change)
                rec = kind.promote(ctx, rec)
                items.append({"kind": rec.kind, "key": rec.key, "revision": rec.revision, "action": change.action, "status": rec.status.value,
                              "risk": rec.risk.value if rec.risk else None, "route": rec.route.value if rec.route else None,
                              "findings": dict(Counter(f.severity.value for f in rec.findings)),
                              "attempts": len(rec.provenance.get("attempts", []))})
        if mode == Route.BATCH:
            items += self.promote_pending(ctx)
        self.store.audit(app, actor, f"reconciliar:{mode.value}", {"version": spec.version, "changes": len(items)})
        report = self.report(ctx, items, admission, started)
        if mode == Route.BATCH:
            self.save_report(report)
        return report

    def promote_pending(self, ctx: BuildContext) -> list[dict[str, Any]]:
        """Promociona candidatos que esperaban a que se publicara la especificación (G6)."""
        out = []
        screen = ScreenKind()
        for rec in self.store.current(ctx.app, "screen"):
            if rec.status == ArtifactStatus.CANDIDATE and rec.key in ctx.spec.views:
                new = screen.promote(ctx, rec)
                if new.status != rec.status:
                    out.append({"kind": "screen", "key": rec.key, "revision": rec.revision, "action": "promote", "status": new.status.value,
                                "risk": rec.risk.value if rec.risk else None, "route": rec.route.value if rec.route else None, "findings": {}, "attempts": 0})
        return out

    def resolve(self, intervention_id: int, approve: bool, motive: str, actor: str = "persona") -> dict[str, Any]:
        it = next((i for i in self.store.interventions() if i.id == intervention_id), None)
        if not it or it.status != "abierta":
            raise ValueError("La intervención no existe o ya está resuelta")
        if not approve and not motive.strip():
            raise ValueError("Rechazar exige un motivo")
        kind, rest = it.artifact.split(":", 1)
        key, rev = rest.rsplit("@r", 1)
        rec = next((r for r in self.store.history(it.app, kind, key) if r.revision == int(rev)), None)
        if rec is None:
            raise ValueError("El artefacto ya no existe")
        spec, _ = admit_and_compile(it.app)
        ctx = self.context(it.app, spec)
        self.store.resolve_intervention(intervention_id, "aprobada" if approve else "rechazada", motive)
        self.store.audit(it.app, actor, f"intervencion:{it.type.value}:{'aprobar' if approve else 'rechazar'}", {"artifact": it.artifact, "motive": motive})
        if not approve or it.type.value == "H3":
            # Rechazar o pedir regenerar: el artefacto queda descartado y la próxima reconciliación lo vuelve a construir.
            self.store.set_status(rec, ArtifactStatus.REJECTED)
            return {"intervention": intervention_id, "artifact": it.artifact, "status": ArtifactStatus.REJECTED.value}
        publish(ctx, rec, actor)
        promoted = self.promote_pending(ctx) if kind == "spec" else []
        return {"intervention": intervention_id, "artifact": it.artifact, "status": ArtifactStatus.PUBLISHED.value, "promoted": promoted}

    # ------------------------------------------------------------ informe de conformidad
    def report(self, ctx: BuildContext, items: list[dict[str, Any]], admission: list[Finding], started: str) -> dict[str, Any]:
        screens = {r.key: r for r in self.store.current(ctx.app, "screen")}
        trace = []
        for req in ctx.spec.requirements:
            arts = [{"view": i.split(":", 1)[1], "status": screens[i.split(":", 1)[1]].status.value if i.split(":", 1)[1] in screens else "sin artefacto"}
                    for i in req.implementedBy if i.startswith("view:")]
            trace.append({"requirement": req.id, "title": req.titulo, "implementedBy": req.implementedBy, "testedBy": req.testedBy, "artifacts": arts,
                          "covered": bool(req.testedBy)})
        spec_rec = self.store.latest(ctx.app, "spec", "spec")
        return {
            "app": ctx.app, "mode": ctx.mode.value, "profile": ctx.profile.id, "version": ctx.spec.version,
            "spec_status": spec_rec.status.value if spec_rec else None, "started": started, "finished": now_iso(),
            "changes": items,
            "admission": [f.model_dump(mode="json") for f in admission],
            "screens": {k: {"status": r.status.value, "revision": r.revision, "risk": r.risk.value if r.risk else None,
                            "blocking": sum(f.severity == Severity.BLOCKING for f in r.findings)} for k, r in screens.items()},
            "traceability": trace,
            "interventions": [i.model_dump(mode="json") for i in self.store.interventions(ctx.app, "abierta")],
        }

    def save_report(self, report: dict[str, Any]) -> Path:
        folder = settings().data_dir / "reports" / report["app"]
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        (folder / f"{stamp}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        md = folder / f"{stamp}.md"
        md.write_text(render_markdown(report), encoding="utf-8")
        return md


def render_markdown(r: dict[str, Any]) -> str:
    lines = [f"# Informe de conformidad · {r['app']}", "",
             f"- Versión de especificación: `{r['version']}` ({r['spec_status']})", f"- Modo: {r['mode']} · Perfil: {r['profile']}",
             f"- Inicio: {r['started']} · Fin: {r['finished']}", "", "## Cambios", "",
             "| Tipo | Clave | Acción | Estado | Riesgo | Ruta | Intentos | Hallazgos |", "|---|---|---|---|---|---|---|---|"]
    for c in r["changes"]:
        lines.append(f"| {c['kind']} | {c['key']} | {c['action']} | {c['status']} | {c['risk'] or ''} | {c['route'] or ''} | {c['attempts']} | "
                     f"{', '.join(f'{k}: {v}' for k, v in c['findings'].items())} |")
    lines += ["", "## Trazabilidad", "", "| Requisito | Implementado por | Probado por | Pantallas |", "|---|---|---|---|"]
    for t in r["traceability"]:
        arts = ", ".join(f"{a['view']} ({a['status']})" for a in t["artifacts"])
        lines.append(f"| {t['requirement']} {t['title']} | {', '.join(t['implementedBy']) or '—'} | {', '.join(t['testedBy']) or '**sin pruebas**'} | {arts or '—'} |")
    lines += ["", "## Intervenciones abiertas", ""]
    lines += [f"- #{i['id']} {i['type']} · {i['artifact']} · {i['role']}: {i['reason']}" for i in r["interventions"]] or ["- Ninguna"]
    return "\n".join(lines) + "\n"


__all__ = ["BuildError", "Reconciler", "SpecKind", "ScreenKind", "admit_and_compile", "app_dir", "list_apps", "render_markdown"]
