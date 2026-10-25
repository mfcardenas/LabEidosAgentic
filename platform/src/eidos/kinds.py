"""Tipos de artefacto: el punto de extensión del reconciliador (ADR-03).

Cada tipo declara cómo planificar, construir (generar + verificar + reparar) y promocionar sus artefactos.
Añadir una capacidad es añadir un tipo aquí, no modificar el reconciliador (F5).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .agents import compose
from .catalog import Catalog
from .contracts import (
    ArtifactRecord,
    ArtifactStatus,
    Autonomy,
    CompiledSpec,
    Finding,
    Intervention,
    InterventionType,
    Route,
    Severity,
)
from .guard import verify_screen
from .guard.conformance import run_conformance
from .llm import LLMError, Profile
from .patterns import base_patterns, related_views
from .policy import Decision, classify, spec_publish_autonomy
from .store import Store

Action = Literal["create", "revalidate", "consolidate", "retire"]


@dataclass
class BuildContext:
    app: str
    spec: CompiledSpec
    catalog: Catalog
    store: Store
    profile: Profile
    mode: Route
    keys: set[str] | None = None
    force: set[str] = field(default_factory=set)
    log: list[dict[str, Any]] = field(default_factory=list)

    @property
    def spec_published(self) -> bool:
        rec = self.store.published(self.app, "spec", "spec")
        return bool(rec and rec.document.get("version") == self.spec.version)


@dataclass
class Change:
    kind: str
    key: str
    action: Action
    fingerprints: dict[str, str]
    previous: ArtifactRecord | None = None
    decision: Decision | None = None


class ArtifactKind(Protocol):
    name: str
    def plan(self, ctx: BuildContext) -> list[Change]: ...
    def build(self, ctx: BuildContext, change: Change) -> ArtifactRecord: ...
    def promote(self, ctx: BuildContext, rec: ArtifactRecord) -> ArtifactRecord: ...


def blocking(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.severity == Severity.BLOCKING]


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def publish(ctx: BuildContext, rec: ArtifactRecord, actor: str) -> ArtifactRecord:
    rec = ctx.store.set_status(rec, ArtifactStatus.PUBLISHED)
    ctx.store.supersede(rec)
    ctx.store.audit(ctx.app, actor, "publicar", {"artifact": rec.ref})
    return rec


# ---------------------------------------------------------------- especificación compilada

class SpecKind:
    name = "spec"

    def plan(self, ctx: BuildContext) -> list[Change]:
        latest = ctx.store.latest(ctx.app, "spec", "spec")
        # Misma versión: ya está publicada, pendiente o rechazada (si se rechazó, se espera a que cambien las entradas).
        if latest and latest.document.get("version") == ctx.spec.version:
            return []
        return [Change("spec", "spec", "create", ctx.spec.fingerprints, ctx.store.published(ctx.app, "spec", "spec"))]

    def build(self, ctx: BuildContext, change: Change) -> ArtifactRecord:
        prev = change.previous.fingerprints if change.previous else {}
        diff = sorted(k for k in set(prev) | set(change.fingerprints) if prev.get(k) != change.fingerprints.get(k))
        rec = ctx.store.save(ArtifactRecord(app=ctx.app, kind="spec", key="spec", revision=0, status=ArtifactStatus.CANDIDATE,
                                            document=ctx.spec.model_dump(mode="json"), fingerprints=change.fingerprints,
                                            findings=ctx.spec.ambiguities, provenance={"changed": diff}))
        return rec

    def promote(self, ctx: BuildContext, rec: ArtifactRecord) -> ArtifactRecord:
        if spec_publish_autonomy(ctx.spec) in (Autonomy.A2, Autonomy.A3) and not ctx.spec.ambiguities:
            return publish(ctx, rec, "sistema")
        rec = ctx.store.set_status(rec, ArtifactStatus.PENDING_APPROVAL)
        role = "funcional" if ctx.spec.ambiguities else "desarrollador"
        ctx.store.open_intervention(Intervention(
            app=ctx.app, type=InterventionType.H1, artifact=rec.ref, role=role,
            reason="Aprobar la especificación compilada" + (" (hay ambigüedades)" if ctx.spec.ambiguities else ""),
            evidence={"version": ctx.spec.version, "changed": rec.provenance.get("changed", []),
                      "ambiguities": [f.model_dump(mode="json") for f in ctx.spec.ambiguities]}))
        return rec


# ---------------------------------------------------------------- pantallas

class ScreenKind:
    name = "screen"

    def dependencies(self, ctx: BuildContext, view_id: str) -> dict[str, str]:
        spec, view = ctx.spec, ctx.spec.views[view_id]
        fp = spec.fingerprints
        e = spec.entities[view.entidad]
        deps = {k: fp[k] for k in (f"view:{view_id}", f"entity:{view.entidad}", "voice", "design_rules", f"tests:{view_id}") if k in fp}
        for f in e.campos.values():
            if f.tipo == "referencia" and f"entity:{f.entidad}" in fp:
                deps[f"entity:{f.entidad}"] = fp[f"entity:{f.entidad}"]
        for r in e.reglas:
            deps[f"rule:{r}"] = fp.get(f"rule:{r}", "")
        if view.comando:
            deps[f"command:{view.comando}"] = fp.get(f"command:{view.comando}", "")
        for rv in related_views(spec, view.entidad).values():
            deps[f"view:{rv}"] = fp.get(f"view:{rv}", "")
        deps[f"recipe:{view.patron}"] = fp.get(f"recipe:{view.patron}") or _h(base_patterns()[view.patron]["receta"])
        deps["catalog"] = ctx.catalog.fingerprint
        deps["profile"] = ctx.profile.id
        return deps

    def plan(self, ctx: BuildContext) -> list[Change]:
        changes: list[Change] = []
        for vid in ctx.spec.views:
            if ctx.keys is not None and vid not in ctx.keys:
                continue
            decision = classify(ctx.spec.views[vid], ctx.spec)
            if decision.route == Route.MANUAL:
                continue
            if ctx.mode == Route.ON_DEMAND and decision.route != Route.ON_DEMAND:
                continue
            deps = self.dependencies(ctx, vid)
            latest = ctx.store.latest(ctx.app, "screen", vid)
            published = ctx.store.published(ctx.app, "screen", vid)
            if vid in ctx.force:
                # Regeneración pedida por una persona: la versión publicada sigue sirviéndose hasta que la nueva supere las puertas.
                changes.append(Change("screen", vid, "create", deps, published or latest, decision))
                continue
            same = lambda r, deps=deps: r is not None and {k: v for k, v in r.fingerprints.items() if k != "profile"} == {k: v for k, v in deps.items() if k != "profile"}
            if latest and same(latest) and latest.status in (ArtifactStatus.PUBLISHED, ArtifactStatus.CANDIDATE,
                                                               ArtifactStatus.PENDING_APPROVAL, ArtifactStatus.ESCALATED):
                continue
            if latest and same(latest) and latest.status == ArtifactStatus.PROVISIONAL:
                if ctx.mode == Route.BATCH:
                    changes.append(Change("screen", vid, "consolidate", deps, latest, decision))
                continue
            if published and not same(published):
                changes.append(Change("screen", vid, "revalidate", deps, published, decision))
            elif not published or not same(published):
                changes.append(Change("screen", vid, "create", deps, latest, decision))
        if ctx.keys is None:
            for rec in ctx.store.current(ctx.app, "screen"):
                if rec.key not in ctx.spec.views and rec.status != ArtifactStatus.RETIRED:
                    changes.append(Change("screen", rec.key, "retire", rec.fingerprints, rec))
        return changes

    def verify(self, ctx: BuildContext, view_id: str, document: Any) -> tuple[dict[str, Any], list[Finding]]:
        view = ctx.spec.views[view_id]
        doc, findings = verify_screen(document, view, ctx.spec, ctx.catalog)
        if not blocking(findings):
            findings += run_conformance(doc, view_id, ctx.spec)
        artifact = f"screen:{view_id}"
        return doc, [f.model_copy(update={"artifact": artifact}) for f in findings]

    def build(self, ctx: BuildContext, change: Change) -> ArtifactRecord:
        assert change.decision is not None or change.action == "retire"
        if change.action == "retire":
            assert change.previous is not None
            return ctx.store.save(change.previous.model_copy(update={"status": ArtifactStatus.RETIRED, "provenance": {"retired": True}}))
        d = change.decision
        assert d is not None
        attempts: list[dict[str, Any]] = []
        doc: dict[str, Any] = {}
        findings: list[Finding] = []
        to_fix: list[Finding] | None = None
        if change.action in ("revalidate", "consolidate") and change.previous:
            doc, findings = self.verify(ctx, change.key, change.previous.document)
            attempts.append({"action": change.action, "blocking": len(blocking(findings))})
            to_fix = blocking(findings) or None
            if to_fix and change.previous.document:
                doc = change.previous.document
        if change.action == "create" or to_fix:
            for i in range(1 + d.retries):
                try:
                    value, meta = compose(ctx.spec, ctx.spec.views[change.key], ctx.catalog, ctx.profile, to_fix)
                except LLMError as e:
                    findings = [Finding(code=f"LLM_{e.code.upper()}", severity=Severity.BLOCKING, layer="G3", source="llm", message=str(e),
                                        artifact=f"screen:{change.key}")]
                    attempts.append({"attempt": i + 1, "error": e.code})
                    break
                doc, findings = self.verify(ctx, change.key, value)
                attempts.append({"attempt": i + 1, "repair": bool(to_fix), "blocking": len(blocking(findings)),
                                 "model": meta.get("model"), "seconds": meta.get("seconds")})
                if not blocking(findings):
                    break
                to_fix = blocking(findings) + [f for f in findings if f.severity == Severity.MAJOR]
        status = (ArtifactStatus.ESCALATED if blocking(findings)
                  else ArtifactStatus.PROVISIONAL if ctx.mode == Route.ON_DEMAND else ArtifactStatus.CANDIDATE)
        rec = ctx.store.save(ArtifactRecord(
            app=ctx.app, kind="screen", key=change.key, revision=0, status=status, risk=d.risk, route=d.route, document=doc,
            fingerprints=change.fingerprints, findings=findings,
            provenance={"action": change.action, "attempts": attempts, "profile": ctx.profile.id, "reasons": list(d.reasons),
                        "requirements": [r.id for r in ctx.spec.requirements if f"view:{change.key}" in r.implementedBy]}))
        if status == ArtifactStatus.ESCALATED:
            ctx.store.open_intervention(Intervention(
                app=ctx.app, type=InterventionType.H3, artifact=rec.ref, role="desarrollador",
                reason=f"No se consiguió una pantalla válida tras {len(attempts)} intento(s)",
                evidence={"findings": [f.model_dump(mode="json") for f in blocking(findings)], "attempts": attempts},
                options=["regenerar", "rechazar"]))
        return rec

    def promote(self, ctx: BuildContext, rec: ArtifactRecord) -> ArtifactRecord:
        """G5-G6: publica según autonomía si la especificación está publicada; si no, pide aprobación (H4)."""
        if rec.status != ArtifactStatus.CANDIDATE or not ctx.spec_published:
            return rec
        if any(f"view:{rec.key}" in r.implementedBy and not r.testedBy for r in ctx.spec.requirements):
            return rec  # RP-05: un requisito sin pruebas bloquea la publicación
        d = classify(ctx.spec.views[rec.key], ctx.spec)
        majors = [f for f in rec.findings if f.severity == Severity.MAJOR]
        if d.auto_publish and not majors:
            return publish(ctx, rec, "sistema")
        rec = ctx.store.set_status(rec, ArtifactStatus.PENDING_APPROVAL)
        ctx.store.open_intervention(Intervention(
            app=ctx.app, type=InterventionType.H4, artifact=rec.ref, role="desarrollador",
            reason=f"Clase {d.risk.value}: {', '.join(d.reasons)}" + (f" · {len(majors)} hallazgo(s) mayor(es)" if majors else ""),
            evidence={"findings": [f.model_dump(mode="json") for f in rec.findings], "provenance": rec.provenance}))
        return rec


KINDS: list[ArtifactKind] = [SpecKind(), ScreenKind()]
