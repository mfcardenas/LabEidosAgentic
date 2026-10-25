"""Carga del paquete de entradas (G0) y compilación de la especificación (G1)."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ..contracts import (
    AppManifest,
    CommandSpec,
    CompiledRequirement,
    CompiledSpec,
    ConformanceTest,
    EntitySpec,
    Finding,
    InputBundle,
    Requirement,
    RuleSpec,
    Severity,
    ViewSpec,
    Voice,
)
from ..patterns import base_patterns

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)$", re.S)


class _Loader(yaml.SafeLoader):
    """YAML con booleanos solo true/false: en español «no» y «si» son palabras, no booleanos."""


_Loader.yaml_implicit_resolvers = {k: [r for r in v if r[0] != "tag:yaml.org,2002:bool"] for k, v in yaml.SafeLoader.yaml_implicit_resolvers.items()}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF"))


def load_yaml(text: str) -> Any:
    return yaml.load(text, Loader=_Loader)  # noqa: S506 - _Loader deriva de SafeLoader


def _finding(code: str, message: str, path: str = "", severity: Severity = Severity.BLOCKING, layer: str = "G0") -> Finding:
    return Finding(code=code, severity=severity, layer=layer, message=message, path=path, source="specs")


def _yaml(file: Path) -> Any:
    return load_yaml(file.read_text(encoding="utf-8")) if file.is_file() else None


def _validation(e: ValidationError, file: str) -> list[Finding]:
    return [_finding("INPUT_INVALID", f"{'.'.join(map(str, err['loc']))}: {err['msg']}", file) for err in e.errors()]


def _sections(body: str) -> dict[str, list[str] | str]:
    out: dict[str, list[str] | str] = {}
    current = None
    for line in body.splitlines():
        if line.startswith("## "):
            current = line[3:].strip().lower()
            out[current] = []
        elif current is not None and line.strip():
            bucket = out[current]
            assert isinstance(bucket, list)
            bucket.append(line.strip())
    return out


def _bullets(lines: list[str] | str | None) -> list[str]:
    return [ln[2:].strip() for ln in (lines or []) if isinstance(ln, str) and ln.startswith(("- ", "* "))]


def load_requirement(file: Path) -> Requirement:
    m = FRONTMATTER.match(file.read_text(encoding="utf-8"))
    if not m:
        raise ValueError("falta la cabecera --- ... ---")
    head = load_yaml(m.group(1)) or {}
    sec = _sections(m.group(2))
    objetivo = " ".join(x for x in sec.get("objetivo", []) if isinstance(x, str))
    return Requirement(**head, objetivo=objetivo, reglas=_bullets(sec.get("reglas")),
                       criterios=_bullets(sec.get("criterios de aceptación")), fichero=file.as_posix())


def load_bundle(app_dir: Path) -> tuple[InputBundle | None, list[Finding]]:
    """G0 · Admisión: valida cada fichero contra su contrato y devuelve hallazgos localizados."""
    findings: list[Finding] = []
    rel = lambda p: p.relative_to(app_dir).as_posix()  # noqa: E731

    def parse(model, data, file):
        try:
            return model.model_validate(data)
        except ValidationError as e:
            findings.extend(_validation(e, file))
            return None

    manifest = parse(AppManifest, _yaml(app_dir / "eidos.yaml") or {}, "eidos.yaml")

    requirements = []
    for f in sorted((app_dir / "funcional" / "requisitos").glob("*.md")):
        try:
            requirements.append(load_requirement(f))
        except (ValidationError, ValueError) as e:
            findings.extend(_validation(e, rel(f)) if isinstance(e, ValidationError) else [_finding("INPUT_INVALID", str(e), rel(f))])

    entities = {}
    for f in sorted((app_dir / "tecnico" / "entidades").glob("*.yaml")):
        if (ent := parse(EntitySpec, _yaml(f), rel(f))):
            entities[ent.entidad] = ent

    def load_list(model, name):
        out = {}
        for i, item in enumerate(_yaml(app_dir / "tecnico" / name) or []):
            if (obj := parse(model, item, f"tecnico/{name}#{i}")):
                if obj.id in out:
                    findings.append(_finding("DUPLICATE_ID", f"Identificador duplicado: {obj.id}", f"tecnico/{name}"))
                out[obj.id] = obj
        return out

    rules, views, commands = load_list(RuleSpec, "reglas.yaml"), load_list(ViewSpec, "vistas.yaml"), load_list(CommandSpec, "comandos.yaml")
    voice = parse(Voice, _yaml(app_dir / "diseno" / "voz.yaml") or {"tono": ""}, "diseno/voz.yaml")
    recipes = {f.stem: (_yaml(f) or {}).get("receta", []) for f in sorted((app_dir / "diseno" / "patrones").glob("*.yaml"))}
    tokens_file = app_dir / "diseno" / "tokens.json"
    tokens = json.loads(tokens_file.read_text(encoding="utf-8")) if tokens_file.is_file() else {}

    tests = []
    for f in sorted((app_dir / "pruebas" / "conformidad").glob("*.yaml")):
        if (t := parse(ConformanceTest, (_yaml(f) or {}) | {"fichero": rel(f)}, rel(f))):
            tests.append(t)

    policies = {f.stem: _yaml(f) or {} for f in sorted((app_dir / "politicas").glob("*.yaml"))}
    seeds = {f.stem: json.loads(f.read_text(encoding="utf-8")) for f in sorted((app_dir / "datos" / "semillas").glob("*.json"))}

    if findings or not manifest or not voice:
        return None, findings
    bundle = InputBundle(manifest=manifest, requirements=requirements, entities=entities, rules=rules, views=views,
                         commands=commands, voice=voice, recipes=recipes, design_rules=_yaml(app_dir / "diseno" / "reglas.yaml") or {},
                         tokens=tokens, tests=tests, policies=policies, seeds=seeds)
    return bundle, findings


def _hash(obj: Any) -> str:
    data = obj.model_dump(mode="json") if hasattr(obj, "model_dump") else obj
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]


def compile_spec(bundle: InputBundle) -> tuple[CompiledSpec | None, list[Finding]]:
    """G1 · Compilación: integridad referencial, ambigüedades, trazabilidad y huellas por fragmento."""
    f: list[Finding] = []
    block = lambda code, msg, path="": f.append(_finding(code, msg, path, layer="G1"))  # noqa: E731
    ambiguous = lambda code, msg, path="": f.append(_finding(code, msg, path, Severity.MAJOR, "G1"))  # noqa: E731
    patterns = base_patterns()
    req_ids = {r.id for r in bundle.requirements}

    for name, e in bundle.entities.items():
        if e.campoTitulo not in e.campos:
            block("ENTITY_TITLE", f"{name}.campoTitulo «{e.campoTitulo}» no es un campo", f"tecnico/entidades/{name}.yaml")
        for fname, fs in e.campos.items():
            if fs.tipo == "enum" and not fs.valores:
                block("ENUM_EMPTY", f"{name}.{fname} es enum sin valores")
            if fs.tipo == "referencia" and fs.entidad not in bundle.entities:
                block("REF_UNKNOWN", f"{name}.{fname} referencia a una entidad inexistente «{fs.entidad}»")
        for r in e.reglas:
            if r not in bundle.rules:
                block("RULE_UNKNOWN", f"{name} cita la regla inexistente «{r}»")
        for mk, m in e.metricas.items():
            if m.campo and m.campo not in e.campos:
                block("METRIC_FIELD", f"{name}.metricas.{mk} usa el campo inexistente «{m.campo}»")
    for r in bundle.rules.values():
        if r.entidad not in bundle.entities:
            block("RULE_ENTITY", f"La regla {r.id} usa la entidad inexistente «{r.entidad}»")
    for c in bundle.commands.values():
        if c.entidad not in bundle.entities:
            block("COMMAND_ENTITY", f"El comando {c.id} usa la entidad inexistente «{c.entidad}»")
        if c.despues.vista not in bundle.views:
            block("COMMAND_AFTER", f"El comando {c.id} navega a una vista inexistente «{c.despues.vista}»")
        for r in c.reglas:
            if r not in bundle.rules:
                block("RULE_UNKNOWN", f"El comando {c.id} cita la regla inexistente «{r}»")
    for v in bundle.views.values():
        if v.entidad not in bundle.entities:
            block("VIEW_ENTITY", f"La vista {v.id} usa la entidad inexistente «{v.entidad}»")
        if v.patron not in patterns:
            block("VIEW_PATTERN", f"La vista {v.id} usa un patrón desconocido «{v.patron}» (opciones: {', '.join(patterns)})")
        if v.patron in ("form", "confirm") and (not v.comando or v.comando not in bundle.commands):
            block("VIEW_COMMAND", f"La vista {v.id} ({v.patron}) necesita un comando existente")
        if v.patron in ("record", "confirm") or (v.comando and bundle.commands.get(v.comando) and bundle.commands[v.comando].tipo == "actualizar"):
            if not v.parametros.id:
                block("VIEW_PARAM_ID", f"La vista {v.id} trabaja sobre un registro y debe declarar parametros.id")
        if not v.requisitos:
            ambiguous("VIEW_NO_REQUIREMENT", f"La vista {v.id} no está ligada a ningún requisito")
        for r in v.requisitos:
            if r not in req_ids:
                block("REQ_UNKNOWN", f"La vista {v.id} cita el requisito inexistente {r}")
    if bundle.manifest.inicio not in bundle.views:
        block("APP_HOME", f"La vista de inicio «{bundle.manifest.inicio}» no existe")
    for s in bundle.manifest.sugerencias:
        if s.vista and s.vista not in bundle.views:
            block("SUGGESTION_VIEW", f"La sugerencia «{s.etiqueta}» apunta a una vista inexistente")
    for t in bundle.tests:
        if t.vista not in bundle.views:
            block("TEST_VIEW", f"La prueba {t.fichero} usa una vista inexistente «{t.vista}»", t.fichero)

    reqs = []
    for r in bundle.requirements:
        impl = [f"view:{v.id}" for v in bundle.views.values() if r.id in v.requisitos]
        impl += [f"command:{c.id}" for c in bundle.commands.values() if r.id in c.requisitos]
        tested = [t.fichero for t in bundle.tests if r.id in t.requisitos or any(f"view:{t.vista}" == i for i in impl)]
        if not r.criterios:
            ambiguous("REQ_NO_CRITERIA", f"{r.id} no tiene criterios de aceptación verificables", r.fichero)
        if not impl:
            ambiguous("REQ_NOT_IMPLEMENTED", f"{r.id} no lo implementa ninguna vista ni comando", r.fichero)
        reqs.append(CompiledRequirement(id=r.id, titulo=r.titulo, actor=r.actor, criticidad=r.criticidad, implementedBy=impl, testedBy=tested))

    if any(x.severity == Severity.BLOCKING for x in f):
        return None, f

    fp: dict[str, str] = {"manifest": _hash(bundle.manifest), "voice": _hash(bundle.voice), "design_rules": _hash(bundle.design_rules),
                          "policies": _hash(bundle.policies)}
    fp |= {f"entity:{k}": _hash(v) for k, v in bundle.entities.items()}
    fp |= {f"rule:{k}": _hash(v) for k, v in bundle.rules.items()}
    fp |= {f"view:{k}": _hash(v) for k, v in bundle.views.items()}
    fp |= {f"command:{k}": _hash(v) for k, v in bundle.commands.items()}
    fp |= {f"recipe:{k}": _hash(v) for k, v in bundle.recipes.items()}
    for v in bundle.views:
        fp[f"tests:{v}"] = _hash([t.model_dump() for t in bundle.tests if t.vista == v])
    version = _hash(fp)

    spec = CompiledSpec(app=bundle.manifest, version=version, requirements=reqs, entities=bundle.entities, rules=bundle.rules,
                        views=bundle.views, commands=bundle.commands, voice=bundle.voice, recipes=bundle.recipes,
                        design_rules=bundle.design_rules, tokens=bundle.tokens, tests=bundle.tests, policies=bundle.policies,
                        ambiguities=[x for x in f if x.severity != Severity.BLOCKING], fingerprints=fp)
    return spec, f
