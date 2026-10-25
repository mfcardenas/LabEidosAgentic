// Modelo SIMULADO con la misma API que Ollama, para probar el runtime sin descargar gpt-oss.
// No piensa: devuelve plantillas fijas por tipo de intent, con algún error a propósito para
// que veas trabajar al Guardián. Uso: npm run demo (lo arranca junto al servidor).
import http from "node:http";

const PORT = Number(process.env.MOCK_PORT || 11435);
const MODELS = ["gpt-oss:20b"];

const TEMPLATES = {
  listado: {
    type: "Screen", title: "Usuarios", subtitle: "Las personas con acceso a la herramienta.",
    actions: [
      { type: "Button", label: "Nuevo usuario", variant: "primary", action: { type: "navigate", intent: "user.create" } },
      { type: "Button", label: "Reparto por rol", variant: "primary", action: { type: "ask", text: "reparto por rol" } }
    ],
    children: [
      { type: "Row", children: [
        { type: "Stat", label: "Total", value: "{{stats.total}}" },
        { type: "Stat", label: "Activos", value: "{{stats.activos}}", tone: "good" },
        { type: "Stat", label: "Inactivos", value: "{{stats.inactivos}}" }
      ] },
      { type: "Alert", when: "filter.active", tone: "info", text: "{{filter.label}} · {{count}} resultado(s)." },
      { type: "Button", when: "filter.active", label: "Ver todos", variant: "ghost", action: { type: "navigate", intent: "user.list", params: {} } },
      { type: "Chart", data: "esto no existe en el catálogo" },
      { type: "Empty", when: "!count", title: "Nadie por aquí", text: "No hay usuarios con este filtro." },
      { type: "Table", when: "count", rows: { $bind: "items" }, columns: [
        { field: "nombre", label: "Nombre" }, { field: "email", label: "Email", format: "email" },
        { field: "rol", label: "Rol", format: "badge" }, { field: "activo", label: "Estado", format: "status" }
      ], rowAction: { type: "navigate", intent: "user.detail", params: { id: "{{row.id}}" } } }
    ]
  },
  detalle: {
    type: "Screen", title: "{{item.nombre}}", subtitle: "{{item.email}}",
    actions: [
      { type: "Button", label: "Editar", variant: "primary", action: { type: "navigate", intent: "user.edit", params: { id: "{{item.id}}" } } },
      { type: "Button", label: "Dar de baja", variant: "danger", action: { type: "delete", id: "{{item.id}}" } }
    ],
    children: [
      { type: "KeyValue", items: [
        { label: "Rol", value: "{{item.rol}}" }, { label: "Departamento", value: "{{item.departamento}}" },
        { label: "Estado", value: "{{item.activo}}" }, { label: "Alta", value: "{{item.alta}}" }
      ] },
      { type: "Button", label: "Volver al listado", variant: "ghost", action: { type: "navigate", intent: "user.list" } }
    ]
  },
  alta: {
    type: "Screen", title: "Nuevo usuario", subtitle: "Rellena los datos. El email no puede repetirse.",
    children: [{ type: "Form", fields: [{ field: "nombre" }, { field: "rol" }, { field: "departamento" }, { field: "activo" }, { field: "alta" }],
      submit: { label: "Crear usuario" }, cancel: { label: "Cancelar", action: { type: "navigate", intent: "user.list" } } }]
  },
  edicion: {
    type: "Screen", title: "Editar usuario", subtitle: "{{item.nombre}}",
    children: [{ type: "Form", fields: [{ field: "nombre" }, { field: "email" }, { field: "rol" }, { field: "departamento" }, { field: "activo" }],
      submit: { label: "Guardar cambios" }, cancel: { label: "Cancelar", action: { type: "navigate", intent: "user.detail", params: { id: "{{item.id}}" } } } }]
  },
  baja: {
    type: "Screen", title: "Dar de baja", subtitle: "Esta acción no se puede deshacer.",
    children: [
      { type: "Alert", tone: "warn", title: "Vas a dar de baja a {{item.nombre}}", text: "{{item.email}} perderá el acceso a la herramienta." },
      { type: "Row", children: [
        { type: "Button", label: "Cancelar", variant: "secondary", action: { type: "navigate", intent: "user.detail", params: { id: "{{item.id}}" } } },
        { type: "Button", label: "Dar de baja", variant: "danger", action: { type: "delete", id: "{{item.id}}" } }
      ] }
    ]
  },
  libre: {
    type: "Screen", title: "Reparto", subtitle: "Cómo se reparten los usuarios.",
    children: [
      { type: "Row", children: [
        { type: "Stat", label: "Total", value: "{{stats.total}}" },
        { type: "Stat", label: "Admins", value: "{{stats.admins}}" },
        { type: "Stat", label: "Altas en 30 días", value: "{{stats.altas30}}" }
      ] },
      { type: "BarList", title: "Por rol", items: { $bind: "stats.porRol" } },
      { type: "BarList", title: "Por departamento", items: { $bind: "stats.porDepartamento" } }
    ]
  }
};

function route(prompt) {
  const msg = (prompt.match(/MENSAJE: «([\s\S]*)»\s*$/) || [])[1]?.toLowerCase() || "";
  const filter = {};
  if (/admin/.test(msg)) filter.rol = "admin";
  if (/editor/.test(msg)) filter.rol = "editor";
  if (/lector/.test(msg)) filter.rol = "lector";
  if (/inactiv/.test(msg)) filter.activo = false;
  else if (/activo/.test(msg)) filter.activo = true;
  if (/resumen|reparto|cu[aá]nt/.test(msg)) return { intent: "view.custom", params: { key: "reparto" }, title: "Reparto", brief: "Reparto de usuarios por rol y por departamento", reply: "Te preparo un reparto por rol y departamento." };
  const alta = msg.match(/(?:alta|nuevo|nueva|crea)\s+(?:de\s+|a\s+)?([a-záéíóúñ]+)/i);
  if (alta) return { intent: "user.create", params: { prefill: { nombre: alta[1][0].toUpperCase() + alta[1].slice(1) } }, reply: "Te abro el alta con el nombre ya puesto." };
  if (Object.keys(filter).length) return { intent: "user.list", params: { filter }, reply: "Te enseño la lista filtrada." };
  return { intent: "none", reply: "(Modelo simulado) Solo entiendo filtros por rol o estado, altas y repartos." };
}

http.createServer((req, res) => {
  if (req.method === "GET" && req.url === "/api/tags") {
    res.writeHead(200, { "Content-Type": "application/json" });
    return res.end(JSON.stringify({ models: MODELS.map(m => ({ name: m, model: m })) }));
  }
  if (req.method === "POST" && req.url === "/api/chat") {
    let body = "";
    req.on("data", c => (body += c));
    req.on("end", () => {
      const prompt = JSON.parse(body).messages?.at(-1)?.content || "";
      let out;
      if (prompt.includes("Eres el Intérprete")) out = route(prompt);
      else if (prompt.includes("Eres el Compositor")) out = TEMPLATES[(prompt.match(/^tipo: (\w+)/m) || [])[1]] || TEMPLATES.listado;
      else out = { ok: true, saludo: "hola desde el modelo simulado" };
      setTimeout(() => {
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ model: "gpt-oss:20b", message: { role: "assistant", content: JSON.stringify(out), thinking: "(simulado)" }, done: true }));
      }, prompt.includes("Eres el Compositor") ? 1200 : 300);
    });
    return;
  }
  res.writeHead(404).end();
}).listen(PORT, "127.0.0.1", () => console.log(`[mock] Modelo simulado escuchando en http://127.0.0.1:${PORT}`));
