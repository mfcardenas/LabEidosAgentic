"""Perfiles de modelo y adaptadores (ADR-09). Salida estructurada cuando el proveedor la soporta.

Un perfil `external` nunca recibe datos reales de la aplicación (RP-07): los prompts se construyen solo con contratos.
"""
from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..config import env, settings


class LLMError(Exception):
    def __init__(self, code: str, message: str, raw: str = ""):
        super().__init__(message)
        self.code, self.raw = code, raw


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    provider: str  # fake | ollama | openai | azure
    base_url: str = ""
    api_key: str = field(default="", repr=False)
    api_version: str = ""
    models: dict[str, str] = field(default_factory=dict)
    reasoning: dict[str, str] = field(default_factory=dict)
    structured: str = "json"  # schema | json
    external: bool = False
    configured: bool = True

    def model(self, agent: str) -> str:
        return self.models.get(agent) or self.models.get("default", "")

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "provider": self.provider, "base_url": self.base_url, "models": self.models,
                "structured": self.structured, "external": self.external, "configured": self.configured}


def profiles() -> dict[str, Profile]:
    local_provider = env("LLM_PROVIDER", "ollama")
    az_endpoint, az_key, az_dep = env("AZURE_OPENAI_ENDPOINT").rstrip("/"), env("AZURE_OPENAI_API_KEY"), env("AZURE_OPENAI_CHAT_DEPLOYMENT")
    return {
        "fake": Profile(id="fake", label="Determinista (plantillas de respaldo)", provider="fake", models={"default": "fake"}),
        "local": Profile(
            id="local", label=f"Local · {local_provider}", provider=local_provider,
            base_url=env("LLM_BASE_URL", "http://localhost:11434").rstrip("/"), api_key=env("LLM_API_KEY"),
            models={"composer": env("COMPOSER_MODEL", "gpt-oss:20b"), "interpreter": env("ROUTER_MODEL", "gpt-oss:20b")},
            reasoning={"composer": env("COMPOSER_REASONING", "medium"), "interpreter": env("ROUTER_REASONING", "low")},
            structured="schema" if local_provider == "ollama" else "json"),
        "azure": Profile(
            id="azure", label="Cloud · Azure OpenAI", provider="azure", base_url=az_endpoint, api_key=az_key,
            api_version=env("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"), models={"default": az_dep},
            structured="json", external=True, configured=bool(az_endpoint and az_key and az_dep)),
    }


def get_profile(name: str | None = None) -> Profile:
    name = name or settings().profile
    p = profiles().get(name)
    if not p:
        raise LLMError("bad_profile", f"No existe el perfil «{name}» (opciones: {', '.join(profiles())})")
    if not p.configured:
        raise LLMError("not_configured", f"El perfil {p.label} no está configurado")
    return p


def extract_json(text: str) -> Any:
    for candidate in (text, *(m.group(1) for m in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", text))):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        try:
            return json.loads(text[a:b + 1])
        except json.JSONDecodeError:
            pass
    raise LLMError("invalid_json", "La respuesta del modelo no es JSON válido", text[:2000])


def complete_json(profile: Profile, agent: str, prompt: str, schema: dict[str, Any] | None = None,
                  fake: Callable[[], Any] | None = None) -> tuple[Any, dict[str, Any]]:
    """Una llamada al modelo que debe devolver JSON. Devuelve (valor, metadatos)."""
    t0 = time.monotonic()
    model = profile.model(agent)
    meta = {"profile": profile.id, "model": model, "agent": agent}
    if profile.provider == "fake":
        if fake is None:
            raise LLMError("fake_unavailable", f"El perfil fake no sabe responder al agente {agent}")
        return fake(), meta | {"seconds": 0.0}

    messages = [{"role": "user", "content": prompt}]
    headers = {"Content-Type": "application/json"}
    if profile.provider == "ollama":
        url = f"{profile.base_url}/api/chat"
        body: dict[str, Any] = {"model": model, "messages": messages, "stream": False, "options": {"num_ctx": int(env("LLM_NUM_CTX", "16384"))},
                                "format": schema if (schema and profile.structured == "schema") else "json"}
        if profile.reasoning.get(agent):
            body["think"] = profile.reasoning[agent]
    elif profile.provider == "azure":
        url = f"{profile.base_url}/openai/deployments/{model}/chat/completions?api-version={profile.api_version}"
        body = {"messages": messages, "response_format": {"type": "json_object"}}
        headers["api-key"] = profile.api_key
    else:
        url = f"{profile.base_url}/chat/completions"
        body = {"model": model, "messages": messages, "response_format": {"type": "json_object"}}
        if profile.api_key:
            headers["Authorization"] = f"Bearer {profile.api_key}"
    try:
        res = httpx.post(url, json=body, headers=headers, timeout=settings().timeout_s)
    except httpx.HTTPError as e:
        raise LLMError("unreachable", f"No hay respuesta de {profile.base_url}: {e}") from e
    if res.status_code >= 400:
        raise LLMError("upstream", f"El proveedor devolvió HTTP {res.status_code}: {res.text[:300]}")
    payload = res.json()
    text = payload.get("message", {}).get("content", "") if profile.provider == "ollama" else \
        (payload.get("choices") or [{}])[0].get("message", {}).get("content", "")
    usage = payload.get("usage") or {"prompt_tokens": payload.get("prompt_eval_count"), "completion_tokens": payload.get("eval_count")}
    return extract_json(text or ""), meta | {"seconds": round(time.monotonic() - t0, 2), "usage": usage}
