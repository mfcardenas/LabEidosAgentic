// Borra la base de datos (usuarios y plantillas) o solo las plantillas guardadas.
//   npm run reset                → empieza de cero (se vuelven a cargar los usuarios de ejemplo)
//   npm run reset -- --pantallas → olvida solo las pantallas generadas
import fs from "node:fs";
import { config } from "../server/config.js";

if (process.argv.includes("--pantallas")) {
  const { openStore } = await import("../server/store.js");
  const store = openStore(config.dbFile);
  const all = store.listScreens();
  for (const s of all) store.deleteScreen(s.key);
  store.close();
  console.log(`Olvidadas ${all.length} plantillas. Los datos siguen intactos.`);
} else {
  let n = 0;
  for (const f of [config.dbFile, `${config.dbFile}-wal`, `${config.dbFile}-shm`]) if (fs.existsSync(f)) { fs.rmSync(f); n++; }
  console.log(n ? "Base de datos borrada. Al arrancar se cargan de nuevo los usuarios de ejemplo." : "No había base de datos que borrar.");
}
