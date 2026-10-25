"""Plano de ejecución: datos de la aplicación, view models, comandos y reglas declarativas.

Genérico: todo se decide con la especificación compilada (F1). Los agentes nunca escriben aquí (RP-02).
"""
from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from ..contracts import CompiledSpec, EntitySpec, FieldSpec, ViewSpec

Record = dict[str, Any]


def _norm(s: Any) -> str:
    return unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower().strip()


class Repository:
    """Almacén genérico de registros por entidad (adaptador SQLite)."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("CREATE TABLE IF NOT EXISTS records (entity TEXT, id TEXT, data TEXT, created TEXT, updated TEXT, PRIMARY KEY (entity, id))")
        self.lock = threading.Lock()

    def list(self, entity: str) -> list[Record]:
        return [{"id": r[0], **json.loads(r[1])} for r in self.db.execute("SELECT id, data FROM records WHERE entity=?", (entity,))]

    def get(self, entity: str, rid: str) -> Record | None:
        r = self.db.execute("SELECT id, data FROM records WHERE entity=? AND id=?", (entity, rid)).fetchone()
        return {"id": r[0], **json.loads(r[1])} if r else None

    def put(self, entity: str, rec: Record) -> None:
        now = datetime.now(UTC).isoformat(timespec="seconds")
        data = json.dumps({k: v for k, v in rec.items() if k != "id"}, ensure_ascii=False)
        with self.lock, self.db:
            self.db.execute("INSERT INTO records VALUES (?,?,?,?,?) ON CONFLICT(entity, id) DO UPDATE SET data=excluded.data, updated=excluded.updated",
                            (entity, rec["id"], data, now, now))

    def delete(self, entity: str, rid: str) -> None:
        with self.lock, self.db:
            self.db.execute("DELETE FROM records WHERE entity=? AND id=?", (entity, rid))

    def count(self, entity: str) -> int:
        return self.db.execute("SELECT COUNT(*) FROM records WHERE entity=?", (entity,)).fetchone()[0]


# ---------------------------------------------------------------- normalización tolerante de valores

def to_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    s = _norm(v)
    return True if s in ("true", "si", "yes", "1") else False if s in ("false", "no", "0") else None


def to_enum(f: FieldSpec, v: Any) -> str | None:
    s = _norm(v)
    for x in f.valores:
        if s in (_norm(x.valor), _norm(x.etiqueta)):
            return x.valor
    s2 = re.sub(r"(as|es|s|a)$", "", s)
    return next((x.valor for x in f.valores if s2 in (_norm(x.valor), _norm(x.etiqueta))), None)


def parse_pairs(v: Any) -> Any:
    if not isinstance(v, str):
        return v
    out = {}
    for part in re.split(r"\s*(?:,|;|&|\by\b)\s*", v):
        if m := re.match(r"^\s*(\w+)\s*[=:]\s*(.+?)\s*$", part):
            out[m.group(1)] = m.group(2).strip("\"'")
    return out


class Data:
    def __init__(self, spec: CompiledSpec, repo: Repository):
        self.spec, self.repo = spec, repo

    def entity(self, name: str) -> EntitySpec:
        return self.spec.entities[name]

    def all(self, e: EntitySpec) -> list[Record]:
        key = e.orden or e.campoTitulo
        return sorted(self.repo.list(e.entidad), key=lambda r: _norm(r.get(key)))

    def with_refs(self, e: EntitySpec, rec: Record) -> Record:
        out = dict(rec)
        for k, f in e.campos.items():
            if f.tipo == "referencia" and f.entidad:
                ref = self.repo.get(f.entidad, str(rec.get(k) or ""))
                out[f"{k}_titulo"] = ref.get(self.entity(f.entidad).campoTitulo) if ref else ""
        return out

    def seed(self, seeds: dict[str, list[Record]]) -> None:
        for name, rows in seeds.items():
            if name in self.spec.entities and self.repo.count(name) == 0:
                for r in rows:
                    self.repo.put(name, r)

    def search(self, text: str) -> list[tuple[str, Record]]:
        """Búsqueda en servidor para resolver registros sin enviar datos al modelo (ADR-10)."""
        t = _norm(text)
        hits = []
        for e in self.spec.entities.values():
            for r in self.repo.list(e.entidad):
                texts = [_norm(r.get(k)) for k, f in e.campos.items() if f.tipo in ("texto", "email")]
                if any(t and (t in x or x in t) for x in texts if x):
                    hits.append((e.entidad, r))
        return hits

    # ------------------------------------------------------------ filtros
    def normalize_filter(self, e: EntitySpec, f: Any) -> dict[str, Any]:
        f = parse_pairs(f)
        out: dict[str, Any] = {}
        if not isinstance(f, dict):
            return out
        for k, v in f.items():
            if v in (None, ""):
                continue
            if k == "q":
                out["q"] = str(v).strip()[:60]
                continue
            fs = e.campos.get(k)
            if not fs:
                continue
            if fs.tipo == "enum" and (x := to_enum(fs, v)) is not None:
                out[k] = x
            elif fs.tipo == "booleano" and (b := to_bool(v)) is not None:
                out[k] = b
            elif fs.tipo == "referencia" and fs.entidad:
                ref = self.repo.get(fs.entidad, str(v)) or next((r for r in self.repo.list(fs.entidad)
                                                                  if _norm(r.get(self.entity(fs.entidad).campoTitulo)) == _norm(v)), None)
                if ref:
                    out[k] = ref["id"]
            elif fs.tipo in ("texto", "email"):
                out[k] = str(v).strip()[:60]
        return out

    def filter_label(self, e: EntitySpec, f: dict[str, Any]) -> str:
        parts = []
        for k, v in f.items():
            if k == "q":
                parts.append(f"Búsqueda: «{v}»")
                continue
            fs = e.campos[k]
            if fs.tipo == "booleano":
                parts.append(f"{fs.etiqueta}: {(fs.si or 'Sí') if v else (fs.no or 'No')}")
            elif fs.tipo == "enum":
                parts.append(f"{fs.etiqueta}: {next((x.etiqueta for x in fs.valores if x.valor == v), v)}")
            elif fs.tipo == "referencia" and fs.entidad:
                ref = self.repo.get(fs.entidad, v)
                parts.append(f"{fs.etiqueta}: {ref.get(self.entity(fs.entidad).campoTitulo) if ref else v}")
            else:
                parts.append(f"{fs.etiqueta}: {v}")
        return " · ".join(parts)

    def matches(self, e: EntitySpec, r: Record, f: dict[str, Any]) -> bool:
        for k, v in f.items():
            if k == "q":
                if not any(_norm(v) in _norm(r.get(n)) for n, fs in e.campos.items() if fs.tipo in ("texto", "email")):
                    return False
            elif e.campos[k].tipo == "booleano":
                if bool(r.get(k)) != v:
                    return False
            elif e.campos[k].tipo in ("texto", "email"):
                if _norm(v) not in _norm(r.get(k)):
                    return False
            elif r.get(k) != v:
                return False
        return True

    # ------------------------------------------------------------ métricas
    def stats(self, e: EntitySpec, rows: list[Record]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, m in e.metricas.items():
            where = lambda r, m=m: all((bool(r.get(c)) == v) if isinstance(v, bool) else r.get(c) == v for c, v in m.donde.items())
            if m.tipo == "conteo":
                out[k] = sum(1 for r in rows if where(r))
            elif m.tipo == "recientes" and m.campo:
                limit = datetime.now(UTC) - timedelta(days=m.dias)
                out[k] = sum(1 for r in rows if r.get(m.campo) and _parse_dt(r[m.campo]) and _parse_dt(r[m.campo]) >= limit)
            elif m.tipo == "reparto" and m.campo:
                fs = e.campos[m.campo]
                if fs.tipo == "enum":
                    out[k] = [{"label": x.etiqueta, "value": sum(1 for r in rows if r.get(m.campo) == x.valor)} for x in fs.valores]
                else:
                    counts: dict[str, int] = {}
                    for r in rows:
                        label = self.with_refs(e, r).get(f"{m.campo}_titulo") if fs.tipo == "referencia" else r.get(m.campo)
                        counts[str(label or "Sin asignar")] = counts.get(str(label or "Sin asignar"), 0) + 1
                    out[k] = [{"label": a, "value": b} for a, b in sorted(counts.items(), key=lambda x: -x[1])]
        return out

    # ------------------------------------------------------------ modelo de datos de una vista
    def view_model(self, view: ViewSpec, params: dict[str, Any]) -> dict[str, Any]:
        e = self.entity(view.entidad)
        if view.patron == "collection":
            rows = self.all(e)
            f = self.normalize_filter(e, params.get("filtro"))
            items = [self.with_refs(e, r) for r in rows if self.matches(e, r, f)]
            return {"items": items, "count": len(items), "stats": self.stats(e, rows),
                    "filter": {"active": bool(f), "label": self.filter_label(e, f), **f}}
        if view.patron == "form" and not params.get("id"):
            item: Record = {"id": ""}
            for k, fs in e.campos.items():
                item[k] = fs.porDefecto if fs.porDefecto is not None else (False if fs.tipo == "booleano" else "")
            item |= self.clean_input(e, params.get("prefill") or {}, partial=True)[0]
            return {"item": self.with_refs(e, item), "options": self.options(e)}
        rec = self.repo.get(e.entidad, str(params.get("id") or ""))
        if not rec:
            raise LookupError(f"No existe ese {e.etiqueta}")
        if view.patron == "form" and params.get("prefill"):
            rec |= self.clean_input(e, params["prefill"], partial=True)[0]
        data: dict[str, Any] = {"item": self.with_refs(e, rec)}
        if view.patron == "form":
            data["options"] = self.options(e)
        return data

    def options(self, e: EntitySpec) -> dict[str, list[dict[str, str]]]:
        out = {}
        for k, f in e.campos.items():
            if f.tipo == "enum":
                out[k] = [{"value": x.valor, "label": x.etiqueta} for x in f.valores]
            elif f.tipo == "referencia" and f.entidad:
                te = self.entity(f.entidad)
                out[k] = [{"value": r["id"], "label": str(r.get(te.campoTitulo, r["id"]))} for r in self.all(te)]
        return out

    # ------------------------------------------------------------ validación de entrada
    def clean_input(self, e: EntitySpec, data: dict[str, Any], partial: bool = False) -> tuple[Record, dict[str, str]]:
        out: Record = {}
        errors: dict[str, str] = {}
        for k, f in e.campos.items():
            if not f.editable or (partial and k not in data):
                continue
            v = data.get(k)
            if v in (None, "") and f.tipo != "booleano":
                if f.requerido and not partial:
                    errors[k] = f"{f.etiqueta} es obligatorio."
                elif not partial:
                    out[k] = f.porDefecto if f.porDefecto is not None else ""
                continue
            if f.tipo in ("texto", "email"):
                s = str(v).strip()
                s = s.lower() if f.minusculas or f.tipo == "email" else s
                if f.tipo == "email" and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", s):
                    errors[k] = "No parece un email válido."
                elif f.min and len(s) < f.min:
                    errors[k] = f"Mínimo {int(f.min)} caracteres."
                elif f.max and len(s) > f.max:
                    errors[k] = f"Máximo {int(f.max)} caracteres."
                out[k] = s
            elif f.tipo == "enum":
                x = to_enum(f, v)
                if x is None:
                    errors[k] = "Valor no permitido."
                out[k] = x
            elif f.tipo == "booleano":
                out[k] = bool(to_bool(v)) if v not in (None, "") else bool(f.porDefecto)
            elif f.tipo == "numero":
                try:
                    n = float(v)
                    if f.min is not None and n < f.min or f.max is not None and n > f.max:
                        errors[k] = "Fuera de rango."
                    out[k] = int(n) if n.is_integer() else n
                except (TypeError, ValueError):
                    errors[k] = "Debe ser un número."
            elif f.tipo in ("fecha", "fechahora"):
                if not _parse_dt(v):
                    errors[k] = "Fecha no válida."
                out[k] = str(v)
            elif f.tipo == "referencia" and f.entidad:
                if not self.repo.get(f.entidad, str(v)):
                    errors[k] = f"No existe ese {self.entity(f.entidad).etiqueta}."
                out[k] = str(v)
        return out, errors


def _parse_dt(v: Any) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=UTC)
    except ValueError:
        return None


# ---------------------------------------------------------------- comandos y reglas declarativas

class Commands:
    def __init__(self, data: Data):
        self.data, self.spec, self.repo = data, data.spec, data.repo

    def execute(self, command_id: str, input: dict[str, Any]) -> dict[str, Any]:
        cmd = self.spec.commands.get(command_id)
        if not cmd:
            return {"ok": False, "errors": {"_": "Ese comando no existe."}}
        e = self.data.entity(cmd.entidad)
        rows = self.repo.list(e.entidad)
        before = None
        if cmd.tipo in ("actualizar", "eliminar"):
            before = self.repo.get(e.entidad, str(input.get("id") or ""))
            if not before:
                return {"ok": False, "errors": {"_": f"Ese {e.etiqueta} ya no existe."}}
        if cmd.tipo == "eliminar":
            after = [r for r in rows if r["id"] != before["id"]]
            if (errors := self.check_rules(cmd.reglas or e.reglas, e, rows, after, None)):
                return {"ok": False, "errors": errors}
            self.repo.delete(e.entidad, before["id"])
            return {"ok": True, "record": before, "next": self.next(cmd, before)}
        clean, errors = self.data.clean_input(e, input, partial=cmd.tipo == "actualizar")
        rec: Record = {**(before or {}), **clean}
        if cmd.tipo == "crear":
            rec["id"] = uuid.uuid4().hex[:8]
            for k, f in e.campos.items():
                if f.auto == "alCrear":
                    rec[k] = datetime.now(UTC).date().isoformat() if f.tipo == "fecha" else datetime.now(UTC).isoformat(timespec="seconds")
        for k, f in e.campos.items():
            if f.unico and rec.get(k) not in (None, "") and k not in errors:
                if any(_norm(r.get(k)) == _norm(rec[k]) and r["id"] != rec.get("id") for r in rows):
                    errors[k] = f"Ya existe otro {e.etiqueta} con ese {f.etiqueta.lower()}."
        if errors:
            return {"ok": False, "errors": errors}
        after = [r for r in rows if r["id"] != rec["id"]] + [rec]
        if (errors := self.check_rules(cmd.reglas or e.reglas, e, rows, after, rec)):
            return {"ok": False, "errors": errors}
        self.repo.put(e.entidad, rec)
        return {"ok": True, "record": rec, "next": self.next(cmd, rec)}

    def next(self, cmd, rec: Record) -> dict[str, Any]:
        return {"view": cmd.despues.vista, "params": {"id": rec["id"]} if cmd.despues.con == "id" else {}}

    def check_rules(self, rule_ids: list[str], e: EntitySpec, before: list[Record], after: list[Record], changed: Record | None) -> dict[str, str]:
        errors: dict[str, str] = {}
        for rid in rule_ids:
            rule = self.spec.rules.get(rid)
            if not rule or rule.entidad != e.entidad:
                continue
            p = rule.params
            if rule.tipo == "minimo":
                where = lambda r, p=p: all((bool(r.get(k)) == v) if isinstance(v, bool) else r.get(k) == v for k, v in p.get("donde", {}).items())
                n_before, n_after = sum(map(where, before)), sum(map(where, after))
                if n_after < int(p.get("min", 1)) <= n_before:
                    errors["_"] = rule.texto
            elif rule.tipo == "sinSolape" and changed:
                ini, fin, grp = p["inicio"], p["fin"], p.get("agrupar")
                a, b = _parse_dt(changed.get(ini)), _parse_dt(changed.get(fin))
                if a and b and a >= b:
                    errors[fin] = "Debe ser posterior al inicio."
                    continue
                donde = p.get("donde", {})
                active = lambda r, donde=donde: all(r.get(k) == v for k, v in donde.items())
                if not active(changed):
                    continue
                for r in after:
                    if r["id"] == changed["id"] or not active(r) or (grp and r.get(grp) != changed.get(grp)):
                        continue
                    c, d = _parse_dt(r.get(ini)), _parse_dt(r.get(fin))
                    if a and b and c and d and a < d and b > c:
                        errors["_"] = rule.texto
                        break
        return errors
