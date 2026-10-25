"""Contratos generados por el sistema: especificación compilada, hallazgos, artefactos e intervenciones."""
from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field

from .inputs import AppManifest, CommandSpec, ConformanceTest, EntitySpec, RuleSpec, ViewSpec, Voice


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Severity(StrEnum):
    BLOCKING = "blocking"
    MAJOR = "major"
    MINOR = "minor"
    AUTOFIXED = "autofixed"


class Finding(BaseModel):
    code: str
    severity: Severity
    layer: str
    message: str
    path: str = ""
    source: str = "guard"
    artifact: str = ""


class CompiledRequirement(BaseModel):
    id: str
    titulo: str
    actor: str
    criticidad: str
    implementedBy: list[str] = Field(default_factory=list)
    testedBy: list[str] = Field(default_factory=list)


class CompiledSpec(BaseModel):
    contract: Literal["eidos-spec/1"] = "eidos-spec/1"
    app: AppManifest
    version: str
    requirements: list[CompiledRequirement]
    entities: dict[str, EntitySpec]
    rules: dict[str, RuleSpec]
    views: dict[str, ViewSpec]
    commands: dict[str, CommandSpec]
    voice: Voice
    recipes: dict[str, list[str]]
    design_rules: dict[str, Any]
    tokens: dict[str, Any]
    tests: list[ConformanceTest]
    policies: dict[str, Any]
    ambiguities: list[Finding] = Field(default_factory=list)
    fingerprints: dict[str, str] = Field(default_factory=dict)


class RiskClass(StrEnum):
    LOW = "baja"
    MEDIUM = "media"
    HIGH = "alta"
    MANUAL = "manual"


class Route(StrEnum):
    ON_DEMAND = "demanda"
    BATCH = "lote"
    MANUAL = "manual"


class Autonomy(StrEnum):
    A0 = "A0"
    A1 = "A1"
    A2 = "A2"
    A3 = "A3"


class ArtifactStatus(StrEnum):
    PLANNED = "planificado"
    ESCALATED = "escalado"
    PROVISIONAL = "provisional"
    CANDIDATE = "candidato"
    PENDING_APPROVAL = "pendiente_aprobacion"
    PUBLISHED = "publicado"
    OUTDATED = "desactualizado"
    RETIRED = "retirado"
    REJECTED = "rechazado"


class ArtifactRecord(BaseModel):
    app: str
    kind: str
    key: str
    revision: int
    status: ArtifactStatus
    risk: RiskClass | None = None
    route: Route | None = None
    document: dict[str, Any]
    fingerprints: dict[str, str] = Field(default_factory=dict)
    findings: list[Finding] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=now_iso)

    @property
    def ref(self) -> str:
        return f"{self.kind}:{self.key}@r{self.revision}"


class InterventionType(StrEnum):
    H1 = "H1"
    H2 = "H2"
    H3 = "H3"
    H4 = "H4"
    H5 = "H5"
    H6 = "H6"


class Intervention(BaseModel):
    id: int | None = None
    app: str
    type: InterventionType
    artifact: str
    role: Literal["funcional", "diseno", "desarrollador"]
    reason: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    options: list[str] = Field(default_factory=lambda: ["aprobar", "rechazar"])
    status: Literal["abierta", "aprobada", "rechazada"] = "abierta"
    motive: str = ""
    created_at: str = Field(default_factory=now_iso)
    resolved_at: str | None = None
