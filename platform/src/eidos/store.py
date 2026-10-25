"""Almacén de artefactos (revisiones inmutables), intervenciones y auditoría. SQLite en laboratorio."""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

from .contracts import ArtifactRecord, ArtifactStatus, Intervention, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
  app TEXT NOT NULL, kind TEXT NOT NULL, key TEXT NOT NULL, revision INTEGER NOT NULL,
  status TEXT NOT NULL, risk TEXT, route TEXT, document TEXT NOT NULL, fingerprints TEXT NOT NULL,
  findings TEXT NOT NULL, provenance TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (app, kind, key, revision)
);
CREATE TABLE IF NOT EXISTS interventions (
  id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT NOT NULL, type TEXT NOT NULL, artifact TEXT NOT NULL, role TEXT NOT NULL,
  reason TEXT NOT NULL, evidence TEXT NOT NULL, options TEXT NOT NULL, status TEXT NOT NULL, motive TEXT NOT NULL,
  created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL, app TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, detail TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()

    # ------------------------------------------------------------ artefactos
    def _row(self, r: sqlite3.Row | None) -> ArtifactRecord | None:
        if r is None:
            return None
        d = dict(r)
        for k in ("document", "fingerprints", "findings", "provenance"):
            d[k] = json.loads(d[k])
        return ArtifactRecord(**d)

    def save(self, rec: ArtifactRecord) -> ArtifactRecord:
        with self.lock, self.db:
            cur = self.db.execute("SELECT COALESCE(MAX(revision), 0) FROM artifacts WHERE app=? AND kind=? AND key=?", (rec.app, rec.kind, rec.key))
            rec = rec.model_copy(update={"revision": cur.fetchone()[0] + 1})
            self.db.execute("INSERT INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                rec.app, rec.kind, rec.key, rec.revision, rec.status.value, rec.risk.value if rec.risk else None,
                rec.route.value if rec.route else None, json.dumps(rec.document, ensure_ascii=False), json.dumps(rec.fingerprints),
                json.dumps([f.model_dump(mode="json") for f in rec.findings], ensure_ascii=False), json.dumps(rec.provenance, ensure_ascii=False),
                rec.created_at))
        return rec

    def set_status(self, rec: ArtifactRecord, status: ArtifactStatus) -> ArtifactRecord:
        with self.lock, self.db:
            self.db.execute("UPDATE artifacts SET status=? WHERE app=? AND kind=? AND key=? AND revision=?",
                            (status.value, rec.app, rec.kind, rec.key, rec.revision))
        return rec.model_copy(update={"status": status})

    def latest(self, app: str, kind: str, key: str) -> ArtifactRecord | None:
        return self._row(self.db.execute("SELECT * FROM artifacts WHERE app=? AND kind=? AND key=? ORDER BY revision DESC LIMIT 1",
                                         (app, kind, key)).fetchone())

    def with_status(self, app: str, kind: str, key: str, *statuses: ArtifactStatus) -> ArtifactRecord | None:
        marks = ",".join("?" * len(statuses))
        return self._row(self.db.execute(
            f"SELECT * FROM artifacts WHERE app=? AND kind=? AND key=? AND status IN ({marks}) ORDER BY revision DESC LIMIT 1",
            (app, kind, key, *(s.value for s in statuses))).fetchone())

    def published(self, app: str, kind: str, key: str) -> ArtifactRecord | None:
        return self.with_status(app, kind, key, ArtifactStatus.PUBLISHED)

    def supersede(self, rec: ArtifactRecord) -> None:
        """Al publicar una revisión, las anteriores publicadas pasan a desactualizado."""
        with self.lock, self.db:
            self.db.execute("UPDATE artifacts SET status=? WHERE app=? AND kind=? AND key=? AND revision<? AND status=?",
                            (ArtifactStatus.OUTDATED.value, rec.app, rec.kind, rec.key, rec.revision, ArtifactStatus.PUBLISHED.value))

    def current(self, app: str, kind: str | None = None) -> list[ArtifactRecord]:
        q = "SELECT a.* FROM artifacts a JOIN (SELECT app, kind, key, MAX(revision) r FROM artifacts GROUP BY app, kind, key) m " \
            "ON a.app=m.app AND a.kind=m.kind AND a.key=m.key AND a.revision=m.r WHERE a.app=?"
        args: list[Any] = [app]
        if kind:
            q += " AND a.kind=?"
            args.append(kind)
        return [r for r in (self._row(x) for x in self.db.execute(q + " ORDER BY a.kind, a.key", args).fetchall()) if r]

    def history(self, app: str, kind: str, key: str) -> list[ArtifactRecord]:
        rows = self.db.execute("SELECT * FROM artifacts WHERE app=? AND kind=? AND key=? ORDER BY revision", (app, kind, key)).fetchall()
        return [r for r in (self._row(x) for x in rows) if r]

    # ------------------------------------------------------------ intervenciones
    def open_intervention(self, it: Intervention) -> Intervention:
        existing = self.db.execute("SELECT id FROM interventions WHERE app=? AND type=? AND artifact=? AND status='abierta'",
                                   (it.app, it.type.value, it.artifact)).fetchone()
        if existing:
            return it.model_copy(update={"id": existing[0]})
        with self.lock, self.db:
            cur = self.db.execute("INSERT INTO interventions (app,type,artifact,role,reason,evidence,options,status,motive,created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                                  (it.app, it.type.value, it.artifact, it.role, it.reason, json.dumps(it.evidence, ensure_ascii=False),
                                   json.dumps(it.options), it.status, it.motive, it.created_at))
        return it.model_copy(update={"id": cur.lastrowid})

    def interventions(self, app: str | None = None, status: str | None = None) -> list[Intervention]:
        q, args = "SELECT * FROM interventions WHERE 1=1", []
        if app:
            q, args = q + " AND app=?", [*args, app]
        if status:
            q, args = q + " AND status=?", [*args, status]
        out = []
        for r in self.db.execute(q + " ORDER BY id", args).fetchall():
            d = dict(r)
            d["evidence"], d["options"] = json.loads(d["evidence"]), json.loads(d["options"])
            out.append(Intervention(**d))
        return out

    def resolve_intervention(self, iid: int, status: str, motive: str) -> Intervention | None:
        with self.lock, self.db:
            self.db.execute("UPDATE interventions SET status=?, motive=?, resolved_at=? WHERE id=? AND status='abierta'", (status, motive, now_iso(), iid))
        found = [i for i in self.interventions() if i.id == iid]
        return found[0] if found else None

    # ------------------------------------------------------------ ajustes
    def get_setting(self, key: str) -> str | None:
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        with self.lock, self.db:
            self.db.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    # ------------------------------------------------------------ auditoría
    def audit(self, app: str, actor: str, action: str, detail: dict[str, Any] | None = None) -> None:
        with self.lock, self.db:
            self.db.execute("INSERT INTO audit (ts, app, actor, action, detail) VALUES (?,?,?,?,?)",
                            (now_iso(), app, actor, action, json.dumps(detail or {}, ensure_ascii=False)))

    def audit_log(self, app: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM audit WHERE app=? ORDER BY id DESC LIMIT ?", (app, limit)).fetchall()
        return [dict(r) | {"detail": json.loads(r["detail"])} for r in rows]
