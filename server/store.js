// Persistencia en SQLite (módulo node:sqlite, incluido en Node 22.13+).
// Los registros se guardan como JSON por entidad: añadir una entidad no requiere migraciones.
import fs from "node:fs";
import path from "node:path";

let DatabaseSync;
try {
  ({ DatabaseSync } = await import("node:sqlite"));
} catch {
  console.error(`\nEidos necesita Node 22.13 o superior (tienes ${process.version}).\nInstala Node 24 LTS desde https://nodejs.org y vuelve a ejecutar npm start.\n`);
  process.exit(1);
}

export function openStore(file) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new DatabaseSync(file);
  db.exec(`
    PRAGMA journal_mode = WAL;
    CREATE TABLE IF NOT EXISTS registros (
      entidad TEXT NOT NULL,
      id TEXT NOT NULL,
      datos TEXT NOT NULL,
      creado TEXT NOT NULL,
      actualizado TEXT NOT NULL,
      PRIMARY KEY (entidad, id)
    );
    CREATE TABLE IF NOT EXISTS pantallas (
      clave TEXT PRIMARY KEY,
      intent TEXT NOT NULL,
      version_spec TEXT NOT NULL,
      plantilla TEXT NOT NULL,
      correcciones TEXT NOT NULL DEFAULT '[]',
      nodos INTEGER,
      peticion TEXT,
      titulo TEXT,
      modelo TEXT,
      segundos REAL,
      creada TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS ajustes (
      clave TEXT PRIMARY KEY,
      valor TEXT NOT NULL
    );
  `);
  const q = {
    list: db.prepare("SELECT id, datos FROM registros WHERE entidad = ?"),
    get: db.prepare("SELECT id, datos FROM registros WHERE entidad = ? AND id = ?"),
    insert: db.prepare("INSERT INTO registros (entidad, id, datos, creado, actualizado) VALUES (?, ?, ?, ?, ?)"),
    update: db.prepare("UPDATE registros SET datos = ?, actualizado = ? WHERE entidad = ? AND id = ?"),
    del: db.prepare("DELETE FROM registros WHERE entidad = ? AND id = ?"),
    count: db.prepare("SELECT COUNT(*) AS n FROM registros WHERE entidad = ?"),
    sGet: db.prepare("SELECT * FROM pantallas WHERE clave = ?"),
    sList: db.prepare("SELECT * FROM pantallas ORDER BY clave"),
    sSave: db.prepare(`INSERT OR REPLACE INTO pantallas
      (clave, intent, version_spec, plantilla, correcciones, nodos, peticion, titulo, modelo, segundos, creada)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`),
    sDel: db.prepare("DELETE FROM pantallas WHERE clave = ?"),
    aGet: db.prepare("SELECT valor FROM ajustes WHERE clave = ?"),
    aSet: db.prepare("INSERT OR REPLACE INTO ajustes (clave, valor) VALUES (?, ?)")
  };
  const row = r => (r ? { id: r.id, ...JSON.parse(r.datos) } : null);
  const screen = r => r && {
    key: r.clave, intent: r.intent, specVersion: r.version_spec, template: JSON.parse(r.plantilla),
    fixes: JSON.parse(r.correcciones || "[]"), nodes: r.nodos, brief: r.peticion, title: r.titulo,
    model: r.modelo, seconds: r.segundos, createdAt: r.creada
  };
  const now = () => new Date().toISOString();

  return {
    list: ent => q.list.all(ent).map(row),
    get: (ent, id) => row(q.get.get(ent, id)),
    insert(ent, rec) { const { id, ...d } = rec; q.insert.run(ent, id, JSON.stringify(d), now(), now()); },
    update(ent, rec) { const { id, ...d } = rec; q.update.run(JSON.stringify(d), now(), ent, id); },
    remove: (ent, id) => q.del.run(ent, id),
    count: ent => q.count.get(ent).n,
    getScreen: key => screen(q.sGet.get(key)),
    listScreens: () => q.sList.all().map(screen),
    saveScreen: d => q.sSave.run(d.key, d.intent, d.specVersion, JSON.stringify(d.template), JSON.stringify(d.fixes || []),
      d.nodes ?? null, d.brief ?? null, d.title ?? null, d.model ?? null, d.seconds ?? null, d.createdAt),
    deleteScreen: key => q.sDel.run(key),
    getSetting: key => q.aGet.get(key)?.valor ?? null,
    setSetting: (key, value) => q.aSet.run(key, String(value)),
    close: () => db.close()
  };
}
