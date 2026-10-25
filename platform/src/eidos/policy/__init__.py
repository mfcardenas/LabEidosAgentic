"""Motor de políticas: clase de riesgo, ruta y autonomía (docs/04-puntos-de-control.md §3).

La clase se calcula a partir de la especificación; los agentes no la eligen.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ..contracts import Autonomy, CompiledSpec, RiskClass, Route, ViewSpec

ORDER = [RiskClass.LOW, RiskClass.MEDIUM, RiskClass.HIGH, RiskClass.MANUAL]


@cache
def _defaults() -> dict[str, Any]:
    return yaml.safe_load((Path(__file__).parent / "defaults.yaml").read_text(encoding="utf-8"))


def _merge(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    out = dict(a)
    for k, v in (b or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def policies(spec: CompiledSpec) -> dict[str, Any]:
    merged = _defaults()
    for doc in (spec.policies or {}).values():
        merged = _merge(merged, doc)
    return merged


@dataclass(frozen=True)
class Decision:
    risk: RiskClass
    route: Route
    generate: Autonomy
    publish: Autonomy
    retries: int
    reasons: tuple[str, ...]

    @property
    def auto_publish(self) -> bool:
        return self.publish in (Autonomy.A2, Autonomy.A3)


def classify(view: ViewSpec, spec: CompiledSpec) -> Decision:
    pol = policies(spec)
    r = pol["riesgo"]
    factors: list[tuple[RiskClass, str]] = [(RiskClass(r["patron"].get(view.patron, "manual")), f"patrón {view.patron}")]
    if view.comando and (cmd := spec.commands.get(view.comando)):
        factors.append((RiskClass(r["comando"][cmd.tipo]), f"comando {cmd.tipo}"))
        if any(spec.rules[x].critica for x in cmd.reglas if x in spec.rules):
            factors.append((RiskClass(r["regla_critica"]), "regla crítica"))
    for req in spec.requirements:
        if f"view:{view.id}" in req.implementedBy:
            factors.append((RiskClass(r["requisito_criticidad"][req.criticidad]), f"{req.id} criticidad {req.criticidad}"))
    risk = max((f[0] for f in factors), key=ORDER.index)
    a = pol["autonomia"][risk.value]
    return Decision(risk=risk, route=Route(a["ruta"]), generate=Autonomy(a["generar"]), publish=Autonomy(a["publicar"]),
                    retries=int(a["reintentos"]), reasons=tuple(why for cls, why in factors if cls == risk))


def spec_publish_autonomy(spec: CompiledSpec) -> Autonomy:
    return Autonomy(policies(spec)["especificacion"]["publicar"])
