# 05 · Contratos y formatos

Todo lo que se intercambia tiene un **esquema versionado**. Los ejemplos usan el dominio piloto (gestión de usuarios) solo como ilustración: ningún formato depende de él.

## 1. Paquete de entradas de una aplicación

Estructura del repositorio de una aplicación (propiedad de las personas):

```
app-usuarios/
  eidos.yaml                     # nombre, versión del contrato, perfiles de modelo permitidos
  funcional/
    requisitos/REQ-001.md …      # un requisito por fichero (o agrupados por épica)
    actores.md
    glosario.md                  # lenguaje ubicuo [R22]
  diseno/
    tokens.json                  # formato DTCG
    voz.md                       # tono y microcopia
    patrones/                    # recetas por patrón (collection, record, form, confirm, dashboard…)
    componentes/                 # extensiones del catálogo (componentes manuales)
  tecnico/
    entidades/Usuario.yaml
    vistas.yaml
    comandos.yaml
    reglas.yaml
    permisos.yaml
    integraciones.yaml
    no-funcionales.yaml          # rendimiento, accesibilidad, privacidad
  pruebas/
    aceptacion/*.feature         # Dado/Cuando/Entonces [R21]
    conformidad/*.yaml           # aserciones sobre documentos de pantalla
    e2e/*.spec.ts                # opcional
  politicas/
    riesgo.yaml
    autonomia.yaml
    modelos.yaml                 # qué perfiles puede usar cada agente; política de datos
```

La **plataforma** (código de los agentes, guardián, renderizador) vive en otro repositorio y se versiona aparte.

## 2. Documento funcional

Formato: Markdown con cabecera estructurada. El cuerpo es libre; la cabecera es obligatoria y se valida en G0.

```markdown
---
id: REQ-003
titulo: Dar de alta un usuario
actor: Administrador
prioridad: alta
criticidad: media          # baja | media | alta (orienta la clase de riesgo)
relacionados: [REQ-001]
---

## Objetivo
Como administrador quiero dar acceso a una persona nueva para que pueda usar la herramienta.

## Reglas
- El email es obligatorio y no puede repetirse.
- El rol por defecto es Lector.

## Criterios de aceptación
- Dado que estoy en el listado, cuando pulso «Nuevo usuario», entonces veo un formulario con nombre, email, departamento, rol y activo.
- Dado un email ya existente, cuando intento crear el usuario, entonces veo un error en el campo email y no se crea.
```

## 3. Especificaciones técnicas

### 3.1 Entidad

```yaml
entidad: Usuario
etiqueta: usuario
plural: usuarios
campoTitulo: nombre
campos:
  nombre:       { tipo: texto, requerido: true, min: 2, max: 80 }
  email:        { tipo: email, requerido: true, unico: true, minusculas: true, sensible: true }
  rol:          { tipo: enum, valores: [admin, editor, lector], porDefecto: lector }
  departamento: { tipo: texto, max: 40 }
  activo:       { tipo: booleano, porDefecto: true }
  alta:         { tipo: fecha, auto: alCrear, soloLectura: true }
reglas: [ultimoAdminActivo]
```

### 3.2 Vista

```yaml
- id: user.list
  requisitos: [REQ-001, REQ-002]
  patron: collection
  entidad: Usuario
  viewModel: { fuente: Usuario, filtro: parametros.filtro, metricas: [total, activos, inactivos, altas30] }
  parametros: { filtro: opcional }
  permisos: [usuarios.leer]
```

### 3.3 Comando

```yaml
- id: usuario.crear
  requisitos: [REQ-003]
  entidad: Usuario
  entrada: { campos: [nombre, email, departamento, rol, activo] }
  reglas: [ultimoAdminActivo]
  permisos: [usuarios.gestionar]
  confirmacion: false
  despues: { vista: user.detail, parametros: { id: $resultado.id } }
```

## 4. Especificación compilada

Es la unión validada de funcional y técnico, con **trazabilidad explícita**. La produce el compilador (agente + validación) y la aprueba una persona (H1).

```json
{
  "contract": "eidos-spec/1",
  "app": "usuarios",
  "version": "2026.10.24-3",
  "requirements": [
    { "id": "REQ-003", "actor": "Administrador", "criticality": "media",
      "implementedBy": ["view:user.create", "command:usuario.crear"],
      "testedBy": ["acc:alta-usuario.feature#1", "acc:alta-usuario.feature#2", "conf:user.create.yaml"] }
  ],
  "entities": { "Usuario": { "...": "..." } },
  "views": { "user.create": { "pattern": "form", "entity": "Usuario", "command": "usuario.crear", "risk": "media" } },
  "commands": { "usuario.crear": { "...": "..." } },
  "ambiguities": [],
  "fingerprints": { "entity:Usuario": "a91f…", "view:user.create": "07c2…" }
}
```

## 5. Catálogo de componentes

Un JSON Schema por componente, con metadatos `x-eidos` que se convierten en instrucciones para el modelo y documentación (fuente única [R9]).

```json
{
  "$id": "eidos-catalog/1/Table",
  "title": "Table",
  "description": "Tabla de registros. La fila puede abrir otra vista.",
  "x-eidos": {
    "version": "1.2.0",
    "container": false,
    "usage": ["Usa format person en el campo título", "Añade Empty con visible negado para listas vacías"],
    "implementation": "renderer/components/table.ts",
    "risk": "baja"
  },
  "type": "object",
  "required": ["id", "component", "rows", "columns"],
  "additionalProperties": false,
  "properties": {
    "id": { "type": "string", "pattern": "^[a-z][a-z0-9-]*$" },
    "component": { "const": "Table" },
    "rows": { "$ref": "#/$defs/Path" },
    "columns": {
      "type": "array", "minItems": 1, "maxItems": 8,
      "items": {
        "type": "object", "required": ["field", "label"], "additionalProperties": false,
        "properties": {
          "field": { "type": "string" },
          "label": { "type": "string" },
          "format": { "enum": ["text", "person", "badge", "status", "date", "email"] }
        }
      }
    },
    "rowAction": { "$ref": "#/$defs/Action" },
    "visible": { "$ref": "#/$defs/Condition" }
  }
}
```

Los **componentes manuales** usan el mismo formato y declaran su implementación. Para el sistema son indistinguibles de los de serie.

## 6. Documento de pantalla

Lista plana de componentes con `id` (alineado con A2UI [R8]). Valores literales o enlazados con `{ "path": "/json/pointer" }`.

```json
{
  "contract": "eidos-ui/1",
  "view": "user.detail",
  "catalog": "eidos-catalog/1",
  "root": "page",
  "components": [
    { "id": "page", "component": "Page", "title": { "path": "/item/nombre" }, "subtitle": { "path": "/item/email" },
      "actions": ["edit", "remove"], "children": ["cols"] },
    { "id": "cols", "component": "Columns", "children": ["profile", "access"] },
    { "id": "profile", "component": "Card", "title": "Perfil", "children": ["profile-kv"] },
    { "id": "profile-kv", "component": "KeyValue", "items": [
      { "label": "Departamento", "value": { "path": "/item/departamento" } } ] },
    { "id": "access", "component": "Card", "title": "Acceso", "children": ["access-kv"] },
    { "id": "access-kv", "component": "KeyValue", "items": [
      { "label": "Rol", "value": { "path": "/item/rol" }, "format": "badge" },
      { "label": "Estado", "value": { "path": "/item/activo" }, "format": "status" } ] },
    { "id": "edit", "component": "Button", "label": "Editar", "variant": "primary",
      "action": { "function": "navigate", "args": { "view": "user.edit", "id": { "path": "/item/id" } } } },
    { "id": "remove", "component": "Button", "label": "Dar de baja", "variant": "secondary",
      "action": { "function": "navigate", "args": { "view": "user.delete", "id": { "path": "/item/id" } } } }
  ],
  "provenance": { "requirements": ["REQ-004"], "pattern": "record@1", "model": "azure/gpt-4o-mini", "attempts": 1 }
}
```

Tipos de acción:

| Acción | Dónde se ejecuta | Ejemplo |
|---|---|---|
| `function` | Cliente, sin red | `navigate`, `setFilter`, `openDialog` |
| `command` | Servidor (comando declarado) | `{ "command": "usuario.desactivar", "input": { "id": { "path": "/item/id" } }, "confirm": true }` |

## 7. Pruebas

### 7.1 Aceptación (comportamiento)

```gherkin
# pruebas/aceptacion/alta-usuario.feature
@REQ-003
Característica: Alta de usuario

  Escenario: Formulario completo
    Dado que estoy en la vista "user.list" como "Administrador"
    Cuando ejecuto la acción primaria
    Entonces veo la vista "user.create"
    Y el formulario contiene los campos "nombre, email, departamento, rol, activo"

  Escenario: Email duplicado
    Dado que existe un usuario con email "ana@ejemplo.com"
    Cuando ejecuto el comando "usuario.crear" con email "ana@ejemplo.com"
    Entonces el comando falla con error en "email"
```

Los pasos (`Dado que estoy en la vista…`, `ejecuto la acción primaria`…) los proporciona la **plataforma** de forma genérica; las personas solo escriben escenarios.

### 7.2 Conformidad (sobre el documento de pantalla, sin navegador)

```yaml
# pruebas/conformidad/user.list.yaml
vista: user.list
requisitos: [REQ-001]
aserciones:
  - tiene_accion_primaria: { vista_destino: user.create }
  - tiene_componente: { tipo: Table, columnas_incluyen: [nombre, email, rol, activo] }
  - tiene_componente: { tipo: Empty, visible_cuando: "not /count" }
  - no_tiene_accion: { command_tipo: destructivo }
  - max_nodos: 40
```

## 8. Hallazgo

```json
{ "code": "BINDING_UNKNOWN_PATH", "severity": "blocking", "layer": "bindings",
  "artifact": "screen:user.detail@r3", "path": "/components/4/items/0/value",
  "message": "La ruta /item/telefono no existe en el modelo de datos de user.detail",
  "autofix": false, "source": "guard" }
```

Fuentes posibles: `guard`, `test:conformance`, `test:acceptance`, `test:e2e`, `judge`, `runtime`.

## 9. Intervención

```json
{
  "id": "INT-0042", "type": "H4", "status": "assigned", "role": "developer",
  "artifact": "screen:user.delete@r2", "risk": "alta",
  "reason": "Clase alta: acción destructiva",
  "evidence": { "report": "…", "preview": "…", "diff": "…", "tests": { "passed": 6, "failed": 0 }, "judge": { "fidelity": 3, "recipe": 3, "clarity": 2, "tone": 3, "coherence": 3 } },
  "options": ["approve", "reject"],
  "due": "2026-10-25T17:00:00Z",
  "decision": null
}
```

## 10. Informe de conformidad

Generado en cada construcción y publicado como comentario en la solicitud de cambio:

| Sección | Contenido |
|---|---|
| Resumen | Versión, artefactos nuevos/cambiados/retirados, estado de puertas, intervenciones abiertas |
| Trazabilidad | Matriz requisito → elemento de especificación → artefactos → pruebas → estado |
| Por artefacto | Clase, ruta, intentos, hallazgos por severidad, pruebas, puntuación del juez, diferencias |
| Calidad por perfil | Válido a la primera, reparaciones, coste, duración |
| Funciones de aptitud | Resultado de F1-F12 (en la plataforma) |

## 11. Eventos cliente-servidor

Alineados con AG-UI [R38]. Transporte NDJSON o SSE.

| Evento | Carga |
|---|---|
| `RUN_STARTED` / `RUN_FINISHED` | `runId` |
| `STEP_STARTED` / `STEP_FINISHED` | agente o componente, texto, duración, hallazgos |
| `SURFACE` | documento de pantalla |
| `STATE_SNAPSHOT` / `STATE_DELTA` | modelo de datos / parche JSON Patch |
| `INTERRUPT` | confirmación requerida (comando destructivo) |
| `RUN_ERROR` | código, mensaje para la persona, detalle técnico |
