# 03 · Ciclo de vida y estados

## 1. Ciclo completo de un cambio

```mermaid
flowchart TB
  subgraph H["Personas"]
    A1[Editan entradas en git<br/>funcional · diseño · técnico · pruebas]
    A2[Abren solicitud de cambio]
  end
  subgraph S["Sistema (plano de control)"]
    B1[G0 Admisión<br/>validar entradas]
    B2[G1 Compilar especificación<br/>detectar ambigüedades]
    B3[G2 Planificar<br/>clasificar vistas y rutas]
    B4[G3 Generar<br/>lote y reparación]
    B5[G4 Verificar<br/>guardián · pruebas · juez]
    B6[Informe de conformidad<br/>+ trazabilidad + diferencias]
    B7[G5 Aprobar<br/>según política]
    B8[G6 Publicar<br/>versión bloqueada]
  end
  subgraph O["Operación"]
    C1[G7 Observar<br/>señales y dependencias]
  end

  A1 --> A2 --> B1 --> B2
  B2 -->|ambigüedades o cambios de especificación| H1{{H1 · Aprobar especificación}}
  H1 --> B3
  B3 -->|clase alta o manual| H2{{H2 · Confirmar plan}}
  B3 -->|clase baja y media| B4
  H2 --> B4
  B4 --> B5
  B5 -->|falla con oráculo| B4
  B5 -->|agotados reintentos| H3{{H3 · Resolver bloqueo}}
  B5 -->|pasa| B6 --> B7
  B7 -->|automático por política| B8
  B7 -->|requiere persona| H4{{H4 · Aprobar publicación}}
  H4 --> B8
  B8 --> C1
  C1 -->|dependencia cambiada o señal| B4
```

Los nodos `H#` son **intervenciones**: el sistema se detiene, crea una solicitud con contexto y espera una decisión registrada. Su catálogo completo está en [04 · Puntos de control](04-puntos-de-control.md#4-catálogo-de-intervenciones).

## 2. Rutas de construcción

| Ruta | Cuándo (decidido por política) | Momento | Verificación | Publicación |
|---|---|---|---|---|
| **Lote** | Clase media y alta, o cualquier vista declarada en la especificación | Al publicar un paquete de entradas (CI) | Completa: G3-G5 + pruebas de aceptación y E2E | Automática (media) o con H4 (alta) |
| **A demanda** | Clase baja: vistas de solo lectura, filtros, resúmenes, peticiones libres | En ejecución, cuando un usuario la pide y no existe | G3-G4 (guardián + conformidad + juez) | Se muestra al usuario; queda como *provisional* hasta el siguiente lote, donde se verifica completa y se consolida |
| **Manual** | La vista requiere una capacidad que no ofrece el catálogo | El desarrollador crea un componente y lo registra en el catálogo | Las mismas pruebas que cualquier vista + revisión de código | Con la versión |

Una vista **nunca** cambia de ruta por decisión del agente: si el clasificador propone otra clase, se registra como sugerencia para H2.

### 2.1 Construcción por lotes

```mermaid
sequenceDiagram
  participant G as git / CI
  participant R as Reconciliador
  participant P as Políticas
  participant C as Compositor
  participant GD as Guardián
  participant T as Pruebas
  participant J as Juez consultivo
  participant S as Almacén
  participant H as Persona

  G->>R: nuevo paquete de entradas (commit)
  R->>R: G0 admisión, G1 compilación (H1 si procede)
  R->>P: plan + clases de riesgo
  P-->>R: rutas y autonomía
  loop por vista afectada (en paralelo)
    R->>C: patrón + catálogo + esquema de datos
    C-->>R: borrador
    R->>GD: verificar
    GD-->>R: hallazgos
    alt hallazgos bloqueantes y reintentos disponibles
      R->>C: reparar con hallazgos
    end
    R->>T: conformidad + aceptación + E2E
    R->>J: rúbrica
  end
  R->>S: candidatos verificados
  R->>G: informe de conformidad + trazabilidad (comentario en la solicitud de cambio)
  alt política exige aprobación
    R->>H: H4 aprobar publicación
    H-->>R: decisión
  end
  R->>S: publicar versión bloqueada
```

### 2.2 Construcción a demanda

```mermaid
sequenceDiagram
  participant U as Usuario
  participant API as API de aplicación
  participant P as Políticas
  participant R as Reconciliador
  participant S as Almacén

  U->>API: vista sin artefacto
  API->>P: ¿clase baja y cuota disponible?
  alt sí
    API->>R: generar (prioridad alta)
    R-->>API: documento verificado G3-G4, estado "provisional"
    API-->>U: pantalla
    R->>S: guardar provisional
  else no
    API-->>U: plantilla de respaldo del patrón
    API->>R: encolar para el próximo lote
  end
```

## 3. Máquinas de estado

### 3.1 Versión del paquete de entradas

```mermaid
stateDiagram-v2
  [*] --> borrador
  borrador --> admitida: G0 superada
  borrador --> rechazada: G0 fallida
  admitida --> compilada: G1 sin ambigüedades bloqueantes
  admitida --> pendiente_aclaracion: ambigüedades
  pendiente_aclaracion --> admitida: H1 resuelta (nueva revisión)
  compilada --> planificada: G2
  planificada --> construida: G3-G5 completadas
  construida --> publicada: G6
  publicada --> sustituida: nueva versión publicada
  publicada --> revertida: reversión
  rechazada --> [*]
  sustituida --> [*]
```

### 3.2 Requisito (trazabilidad)

```mermaid
stateDiagram-v2
  [*] --> propuesto
  propuesto --> especificado: aparece en la especificación compilada
  especificado --> cubierto: tiene al menos una prueba aprobada
  cubierto --> implementado: artefactos que lo materializan publicados
  implementado --> verificado: todas sus pruebas pasan en la versión
  verificado --> aceptado: aprobado por funcional (H5) o por política
  verificado --> implementado: una prueba vuelve a fallar
  aceptado --> obsoleto: retirado del documento funcional
  especificado --> sin_cubrir: no tiene pruebas
  sin_cubrir --> cubierto: prueba aprobada
```

Un requisito `sin_cubrir` **bloquea la publicación** de los artefactos que lo implementan (regla RP-05).

### 3.3 Artefacto de pantalla

```mermaid
stateDiagram-v2
  [*] --> planificado
  planificado --> generando
  generando --> verificando
  verificando --> reparando: hallazgo con oráculo
  reparando --> verificando
  verificando --> escalado: reintentos agotados
  escalado --> generando: H3 decide regenerar
  escalado --> manual: H3 decide ruta manual
  verificando --> provisional: ruta a demanda, G4 superada
  verificando --> candidato: ruta lote, G4 superada
  provisional --> candidato: consolidado en lote
  candidato --> pendiente_aprobacion: política exige persona
  candidato --> publicado: política permite automático
  pendiente_aprobacion --> publicado: H4 aprobada
  pendiente_aprobacion --> generando: H4 rechazada con motivo
  publicado --> desactualizado: cambia una dependencia
  desactualizado --> verificando: revalidación
  publicado --> retirado: la vista desaparece de la especificación
  manual --> candidato: componente registrado y pruebas superadas
  retirado --> [*]
```

Reglas del ciclo:

- **publicado** es inmutable. Cualquier cambio crea una nueva revisión del artefacto.
- **desactualizado** sigue sirviéndose hasta que su sustituto esté publicado (no hay huecos para el usuario).
- **reparando** solo se alcanza desde un hallazgo concreto (prueba, regla o señal). Sin hallazgo no hay reparación.
- El número máximo de reintentos lo fija la política por clase (por defecto: baja 2, media 2, alta 1).

### 3.4 Intervención

```mermaid
stateDiagram-v2
  [*] --> abierta
  abierta --> asignada: rol disponible
  asignada --> resuelta_aprobada
  asignada --> resuelta_rechazada
  asignada --> resuelta_modificada: la persona cambia las entradas
  asignada --> vencida: supera el plazo
  vencida --> asignada: escalado al rol superior
  resuelta_aprobada --> cerrada
  resuelta_rechazada --> cerrada
  resuelta_modificada --> cerrada
  cerrada --> [*]
```

Toda resolución requiere **motivo** cuando es rechazo o modificación; queda en el registro de auditoría con la evidencia que se mostró.

### 3.5 Migración de datos

```mermaid
stateDiagram-v2
  [*] --> propuesta
  propuesta --> simulada: aplicada en copia con datos sintéticos o anonimizados
  simulada --> pendiente_aprobacion: reversible y sin pérdida detectada
  simulada --> bloqueada: pérdida de datos o no reversible
  bloqueada --> propuesta: cambio de especificación
  pendiente_aprobacion --> aprobada: H4 (desarrollador)
  aprobada --> aplicada: con copia de seguridad previa
  aplicada --> verificada: pruebas de datos superadas
  aplicada --> revertida: fallo
  verificada --> [*]
  revertida --> [*]
```

## 4. Revalidación por dependencias

Cada artefacto publicado guarda su **conjunto de dependencias** con huellas:

| Dependencia | Ejemplo | Huella |
|---|---|---|
| Fragmento de especificación | Entidad `Usuario`, vista `user.list`, regla `ultimoAdminActivo` | Hash del fragmento, no de toda la especificación |
| Catálogo | `Table@1.2`, `Card@1.0` | Versión por componente |
| Sistema de diseño | Reglas y receta del patrón `collection` | Hash |
| Pruebas | Pruebas que lo cubren | Hash |
| Perfil de modelo | `azure/gpt-4o-mini@2024-07-18` | Identificador |
| Esquema de datos | Esquema del modelo de datos de la vista | Hash |
| Renderizador | Versión mayor del contrato | Semver [R39] |

Cuando cambia una huella, el reconciliador marca el artefacto como **desactualizado** y lo **revalida**. Solo si la revalidación falla se regenera o repara. Este es el mecanismo de **"reparar antes de que el usuario vea el problema"**.

Un cambio del perfil de modelo **no** invalida artefactos publicados por defecto (están bloqueados). Sí dispara la evaluación del nuevo perfil y, si la política lo indica, una regeneración comparativa que pasa por H4.
