"""Contratos de las entradas humanas (paquete de entradas). Ver docs/05-contratos.md."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FieldType = Literal["texto", "email", "enum", "booleano", "fecha", "fechahora", "numero", "referencia"]
Criticality = Literal["baja", "media", "alta"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Suggestion(Strict):
    etiqueta: str
    vista: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    texto: str | None = None


class AppManifest(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]*$")
    nombre: str
    contrato: Literal["eidos-inputs/1"] = "eidos-inputs/1"
    idioma: str = "es-ES"
    proposito: str
    inicio: str
    sugerencias: list[Suggestion] = Field(default_factory=list)


class Requirement(Strict):
    id: str = Field(pattern=r"^REQ-\d{3,}$")
    titulo: str
    actor: str
    prioridad: Literal["baja", "media", "alta"] = "media"
    criticidad: Criticality = "media"
    relacionados: list[str] = Field(default_factory=list)
    objetivo: str = ""
    reglas: list[str] = Field(default_factory=list)
    criterios: list[str] = Field(default_factory=list)
    fichero: str = ""


class EnumValue(Strict):
    valor: str
    etiqueta: str
    tono: Literal["neutral", "accent", "info", "good", "warn", "bad"] = "neutral"


class FieldSpec(Strict):
    tipo: FieldType
    etiqueta: str
    requerido: bool = False
    min: float | None = None
    max: float | None = None
    unico: bool = False
    minusculas: bool = False
    porDefecto: Any = None
    soloLectura: bool = False
    auto: Literal["alCrear"] | None = None
    valores: list[EnumValue] = Field(default_factory=list)
    entidad: str | None = None
    sensible: bool = False
    si: str | None = None
    no: str | None = None

    @property
    def editable(self) -> bool:
        return not self.soloLectura and self.auto is None


class MetricSpec(Strict):
    tipo: Literal["conteo", "recientes", "reparto"]
    etiqueta: str
    donde: dict[str, Any] = Field(default_factory=dict)
    campo: str | None = None
    dias: int = 30


class EntitySpec(Strict):
    entidad: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    etiqueta: str
    plural: str
    genero: Literal["m", "f"] = "m"
    campoTitulo: str
    orden: str | None = None
    campos: dict[str, FieldSpec]
    metricas: dict[str, MetricSpec] = Field(default_factory=dict)
    reglas: list[str] = Field(default_factory=list)


class RuleSpec(Strict):
    id: str
    tipo: Literal["minimo", "sinSolape"]
    entidad: str
    texto: str
    critica: bool = False
    params: dict[str, Any] = Field(default_factory=dict)


class ViewParams(Strict):
    filtro: bool = False
    id: bool = False
    prefill: bool = False


class ViewSpec(Strict):
    id: str = Field(pattern=r"^[a-z][a-z0-9]*(\.[a-z][a-z0-9-]*)+$")
    titulo: str
    descripcion: str
    patron: str
    entidad: str
    requisitos: list[str] = Field(default_factory=list)
    parametros: ViewParams = Field(default_factory=ViewParams)
    comando: str | None = None
    metricas: list[str] = Field(default_factory=list)


class AfterCommand(Strict):
    vista: str
    con: Literal["id", "ninguno"] = "id"


class CommandSpec(Strict):
    id: str
    tipo: Literal["crear", "actualizar", "eliminar"]
    entidad: str
    etiqueta: str | None = None
    requisitos: list[str] = Field(default_factory=list)
    reglas: list[str] = Field(default_factory=list)
    confirmacion: bool = False
    despues: AfterCommand


class Voice(Strict):
    tono: str
    reglas: list[str] = Field(default_factory=list)


class ConformanceTest(Strict):
    vista: str
    requisitos: list[str] = Field(default_factory=list)
    aserciones: list[dict[str, Any]]
    fichero: str = ""


class InputBundle(Strict):
    """Paquete de entradas cargado y validado (G0)."""
    manifest: AppManifest
    requirements: list[Requirement]
    entities: dict[str, EntitySpec]
    rules: dict[str, RuleSpec]
    views: dict[str, ViewSpec]
    commands: dict[str, CommandSpec]
    voice: Voice
    recipes: dict[str, list[str]] = Field(default_factory=dict)
    design_rules: dict[str, Any] = Field(default_factory=dict)
    tokens: dict[str, Any] = Field(default_factory=dict)
    tests: list[ConformanceTest] = Field(default_factory=list)
    policies: dict[str, Any] = Field(default_factory=dict)
    seeds: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
