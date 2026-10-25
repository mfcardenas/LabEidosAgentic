"""Catálogo de componentes: fuente única de prompt, esquema de salida, validación y documentación (ADR-04)."""
from __future__ import annotations

import copy
import hashlib
import json
from functools import cached_property
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

BASE_DIR = Path(__file__).parent
CONTRACT = "eidos-catalog/1"
DOCUMENT_CONTRACT = "eidos-ui/1"


def _summary(prop: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in prop:
        name = prop["$ref"].rsplit("/", 1)[-1]
        return {"Value": "valor", "Path": "ruta", "Ids": "ids", "Id": "id", "Condition": "condición",
                "Action": "acción", "Navigate": "navegación", "Command": "comando", "Tone": "tono", "Format": "formato"}.get(name, name)
    if "const" in prop:
        return json.dumps(prop["const"])
    if "enum" in prop:
        return " | ".join(map(str, prop["enum"]))
    if prop.get("type") == "array":
        items = prop.get("items", {})
        if items.get("type") == "object":
            req = set(items.get("required", []))
            keys = ", ".join(k if k in req else f"{k}?" for k in items.get("properties", {}))
            return f"[{{{keys}}}]"
        return f"[{_summary(items, defs)}]"
    if prop.get("type") == "object":
        req = set(prop.get("required", []))
        return "{" + ", ".join(k if k in req else f"{k}?" for k in prop.get("properties", {})) + "}"
    return {"string": "texto", "number": "número", "boolean": "sí/no"}.get(prop.get("type", ""), "valor")


class Catalog:
    def __init__(self, extra_dirs: list[Path] | None = None):
        self.defs: dict[str, Any] = json.loads((BASE_DIR / "_defs.json").read_text(encoding="utf-8"))
        self.defs.pop("$comment", None)
        self.components: dict[str, dict[str, Any]] = {}
        for folder in [BASE_DIR, *(extra_dirs or [])]:
            for file in sorted(folder.glob("*.json")):
                if file.name.startswith("_"):
                    continue
                schema = json.loads(file.read_text(encoding="utf-8"))
                schema["$defs"] = self.defs
                self.components[schema["title"]] = schema

    def meta(self, name: str) -> dict[str, Any]:
        return self.components[name].get("x-eidos", {})

    def is_container(self, name: str) -> bool:
        return bool(self.meta(name).get("container"))

    @cached_property
    def validators(self) -> dict[str, Draft202012Validator]:
        return {name: Draft202012Validator(schema) for name, schema in self.components.items()}

    @cached_property
    def fingerprint(self) -> str:
        raw = json.dumps({n: s.get("x-eidos", {}).get("version") for n, s in sorted(self.components.items())} | {"$defs": self.defs}, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:12]

    def screen_schema(self) -> dict[str, Any]:
        """Esquema del documento de pantalla, usado para salida estructurada y exportado a contracts/."""
        items = []
        for schema in self.components.values():
            s = copy.deepcopy(schema)
            for k in ("$id", "$defs", "x-eidos"):
                s.pop(k, None)
            items.append(s)
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": DOCUMENT_CONTRACT,
            "title": "ScreenDocument",
            "type": "object",
            "required": ["contract", "view", "root", "components"],
            "additionalProperties": False,
            "properties": {
                "contract": {"const": DOCUMENT_CONTRACT},
                "view": {"type": "string"},
                "root": {"$ref": "#/$defs/Id"},
                "components": {"type": "array", "minItems": 1, "items": {"anyOf": items}},
            },
            "$defs": self.defs,
        }

    def prompt(self) -> str:
        """Descripción del catálogo para el modelo, derivada de los esquemas (F3)."""
        lines = []
        for name, schema in self.components.items():
            req = set(schema.get("required", []))
            props = ", ".join(
                f"{k}{'' if k in req else '?'}: {_summary(v, self.defs)}"
                for k, v in schema["properties"].items() if k not in ("id", "component")
            )
            usage = "; ".join(self.meta(name).get("usage", []))
            lines.append(f"- {name}: {schema.get('description', '')} Props: {props}.{' Uso: ' + usage + '.' if usage else ''}")
        return "\n".join(lines)
