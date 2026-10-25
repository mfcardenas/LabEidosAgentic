# 09 · Plan de trabajo

Este plan concreta la [hoja de ruta](08-hoja-de-ruta.md) en paquetes de trabajo, tareas y criterios de aceptación. La **Fase 1** se detalla por iteraciones; las siguientes, por paquetes.

## 1. Organización

| Corriente | Responsable | Alcance |
|---|---|---|
| **PL · Plataforma** | Equipo de IA | Contratos, reconciliador, agentes, guardián, políticas, almacén, API |
| **CL · Cliente** | Equipo de IA (apoyo puntual de front) | Renderizador del catálogo, shell, consola de supervisión |
| **AP · Aplicaciones** | Funcional + desarrollador | Paquetes de entradas del piloto (usuarios) y del testigo (reservas): requisitos, diseño, técnico, pruebas, políticas |
| **QA · Calidad** | Desarrollador + equipo de IA | Pruebas de plataforma, funciones de aptitud, batería de evaluación de modelos |
| **OP · Operación** | Equipo de IA | Docker, CI, observabilidad |

Iteraciones de dos semanas. Cada iteración termina con una demo sobre **los dos dominios** y el informe de conformidad.

## 2. Estructura del repositorio

```
platform/                 Plataforma Eidos (Python, paquete `eidos`)
  src/eidos/
    contracts/            modelos Pydantic de entradas, especificación, artefactos, hallazgos
    catalog/              catálogo base: un JSON Schema por componente
    patterns/             patrones base: receta + constructor de respaldo
    specs/                carga (G0) y compilación (G1) del paquete de entradas
    guard/                verificación determinista (capas 1-3) y pruebas de conformidad
    policy/               clases de riesgo, rutas y autonomía
    llm/                  perfiles y adaptadores (fake, ollama, azure, compatible OpenAI)
    agents/               compositor e intérprete (prompts derivados de contratos)
    kinds/                tipos de artefacto (spec, screen)
    runtime/              repositorio, view models, comandos, reglas
    store.py              almacén de artefactos, intervenciones y auditoría
    reconciler.py         bucle de reconciliación
    api.py · cli.py       API HTTP y línea de comandos
  tests/                  pruebas de plataforma y funciones de aptitud
client/                   Renderizador y shell (TypeScript)
apps/
  usuarios/               dominio piloto (paquete de entradas)
  reservas/               dominio testigo (paquete de entradas)
contracts/                JSON Schema exportados (generados por `eidos schemas`)
server/ public/ specs/    Prototipo F0 (se retira al alcanzar paridad en F2)
```

## 3. Fase 1 · Contratos y núcleo

### Iteración 1.1 · Esqueleto de arquitectura *(montada en este repositorio)*

| Id | Tarea | Corriente | Estado |
|---|---|---|---|
| 1.1.1 | Estructura del repositorio, `pyproject`, entorno y CLI | PL | ✅ |
| 1.1.2 | Contratos Pydantic: manifiesto, requisito, entidad, vista, comando, regla, especificación compilada, hallazgo, artefacto, intervención | PL | ✅ |
| 1.1.3 | Catálogo base en JSON Schema (12 componentes) + `$defs` comunes (valor, ruta, condición, acción) | PL | ✅ |
| 1.1.4 | Esquema del documento de pantalla derivado del catálogo; prompt derivado del catálogo | PL | ✅ |
| 1.1.5 | Patrones base (`collection`, `record`, `form`, `confirm`) con receta genérica y constructor de respaldo determinista | PL | ✅ |
| 1.1.6 | Carga y validación del paquete de entradas (G0) y compilación determinista con trazabilidad y huellas (G1) | PL | ✅ |
| 1.1.7 | Guardián capas 1-3 (estructura, enlaces, diseño) con reglas como datos | PL | ✅ |
| 1.1.8 | Pruebas de conformidad declarativas (YAML) sobre documentos de pantalla | PL/QA | ✅ |
| 1.1.9 | Motor de políticas: clase de riesgo, ruta, autonomía, reintentos | PL | ✅ |
| 1.1.10 | Perfiles de modelo y adaptadores (fake, Ollama, Azure, compatible OpenAI) con salida estructurada | PL | ✅ |
| 1.1.11 | Compositor e intérprete con prompts derivados; intérprete **sin datos reales** (búsqueda en servidor) | PL | ✅ |
| 1.1.12 | Almacén de artefactos con revisiones, estados, huellas, intervenciones y auditoría | PL | ✅ |
| 1.1.13 | Reconciliador con tipos de artefacto `spec` y `screen`, reparación con hallazgos, revalidación por dependencias | PL | ✅ |
| 1.1.14 | Runtime genérico: repositorio, view models, comandos, reglas declarativas (`minimo`, `sinSolape`) | PL | ✅ |
| 1.1.15 | API (ejecución + control) y CLI (`validate`, `build`, `serve`, `schemas`, `interventions`) | PL | ✅ |
| 1.1.16 | Paquetes de entradas del piloto (usuarios) y testigo (reservas) | AP | ✅ (borrador para revisión de funcional) |
| 1.1.17 | Renderizador TypeScript con registro de componentes y motor de enlaces JSON Pointer | CL | ✅ |
| 1.1.18 | Funciones de aptitud F1, F2, F3 y RP-07 en pruebas | QA | ✅ |
| 1.1.19 | Contenedor de la plataforma y arranque con `start.ps1 -Plataforma` | OP | ✅ |

**Criterio de salida 1.1:** `eidos build` construye piloto y testigo con el perfil `fake`; todas las pruebas y funciones de aptitud en verde; la aplicación funciona en el navegador con plantillas de respaldo aunque no haya modelo.

**Estado (24/10/2026):** cumplido. 29 pruebas en verde (incluidas F1, F2, F3 y RP-07), `ruff` sin avisos, contenedor `plataforma` operativo.

**Primera medición con modelo real (Azure `gpt-4o-mini`, entrada para 1.2):** 11 de 14 pantallas válidas (8 a la primera, 3 tras reparación); 3 escaladas a H3 por referencias a componentes no definidos o rutas inexistentes. La normalización del guardián ya corrige las desviaciones de forma más frecuentes del modelo (componentes anidados, hijos en línea, `format` dentro del enlace).

### Iteración 1.2 · Generación real y calidad

| Id | Tarea | Corriente | Criterio de aceptación |
|---|---|---|---|
| 1.2.1 | Batería de evaluación (`eval/`): casos del intérprete y del compositor por dominio | QA | Informe por perfil: válido a la primera, reparaciones, duración |
| 1.2.2 | Ajuste de prompts y recetas con Ollama y Azure | PL | ≥ 90 % válidos a la primera en ambos perfiles (F10) |
| 1.2.3 | Tipos TypeScript generados desde `contracts/` en el build del cliente | CL | El build falla si cambia un contrato sin regenerar tipos |
| 1.2.4 | Eventos de ejecución alineados con AG-UI (NDJSON) | PL/CL | Traza de pasos visible en la consola |
| 1.2.5 | Revisión funcional de los paquetes de entradas | AP | Requisitos con criterios verificables (G0 sin avisos) |
| 1.2.6 | CI: `eidos validate` + `eidos build` + pytest en cada cambio | OP | Pipeline en verde para ambos dominios |

**Criterio de salida F1:** piloto y testigo construidos desde sus entradas con dos perfiles reales; 0 datos reales en prompts cloud; ≥ 90 % válidos a la primera.

### Iteración 1.3 · Plataforma por defecto y consola de supervisión *(adelanta 2.E y 2.G)*

| Id | Tarea | Corriente | Estado |
|---|---|---|---|
| 1.3.1 | Perfil de modelo activo persistido y elegible desde consola/CLI (`eidos profile`), con prueba de conexión | PL | ✅ |
| 1.3.2 | API de control: resumen de aplicaciones, artefactos, historial, vista previa de cualquier revisión con datos reales, regeneración con motivo, último informe | PL | ✅ |
| 1.3.3 | Regeneración forzada por las mismas puertas: la versión publicada se sigue sirviendo hasta que la nueva se publique | PL | ✅ |
| 1.3.4 | Traza de ejecución por vista (datos, artefacto, generación a demanda, respaldo) en la vista técnica | PL/CL | ✅ |
| 1.3.5 | Consola de supervisión (`/console.html`): modelo, construcción, intervenciones con evidencia y motivo, pantallas con vista previa, trazabilidad, auditoría | CL | ✅ |
| 1.3.6 | La plataforma es el servicio por defecto (`start.ps1`); el prototipo pasa a opt-in (`-Prototipo`, `-Demo`) | OP | ✅ |
| 1.3.7 | Pruebas de API (consola de punta a punta, JSON obligatorio en escrituras) | QA | ✅ |

**Pendiente para retirar el prototipo (2.G):** intérprete con modelo real evaluado, catálogo de specs y arquitectura visibles en la consola, y eventos en streaming.

## 4. Fase 2 · Puertas, pruebas y consola

| Paquete | Contenido | Corriente |
|---|---|---|
| 2.A Guardián capa 4 | Permisos por actor, campos sensibles, accesibilidad mínima | PL |
| 2.B Pruebas de aceptación | Pasos genéricos Dado/Cuando/Entonces sobre la API (pytest-bdd) | PL/QA |
| 2.C Juez consultivo | Rúbrica configurable, perfil distinto del compositor, calibración | PL |
| 2.D Intervenciones H1-H5 | Plazos, roles, motivo obligatorio, muestreo de auditoría | PL |
| 2.E Consola de supervisión | Intervenciones, informe de conformidad, diferencias, trazabilidad, vista previa | CL |
| 2.F Integración git | Informe como comentario en la solicitud de cambio; publicación al fusionar | OP |
| 2.G Retirada del prototipo | Paridad funcional con F0 (incluida la consola de modelos) | PL/CL |

## 5. Fase 3 · Patrones, regiones y lote

| Paquete | Contenido |
|---|---|
| 3.A Biblioteca de patrones | `dashboard`, `master-detail`, `wizard` |
| 3.B Regiones | Planificador de regiones; generación y verificación por región |
| 3.C Componentes manuales | Registro de componentes propios del desarrollador (F7, F8) |
| 3.D Relaciones | View models multi-entidad; navegación entre entidades relacionadas |
| 3.E Lote en CI | Construcción completa en CI; a demanda acotada en ejecución |

## 6. Fase 4 · Mantenimiento y operación

| Paquete | Contenido |
|---|---|
| 4.A Migraciones | Tipo de artefacto `migration` (Alembic), simulación, reversión, H4 |
| 4.B Señales | Errores de renderizado, enlaces vacíos y peticiones sin artefacto → revalidación/H6 |
| 4.C Reversión | Publicación por puntero; reversión en un paso |
| 4.D Observabilidad | OpenTelemetry, coste y calidad por perfil |
| 4.E Aptitud completa | F4-F12 automatizadas en CI |

## 7. Definición de hecho (todas las tareas)

- Contratos actualizados y exportados (`eidos schemas`).
- Pruebas de plataforma y funciones de aptitud en verde.
- Los **dos** dominios se construyen sin cambios en la plataforma.
- Ningún término de dominio en `platform/` (F1).
- Documentación de arquitectura actualizada si cambia una decisión (nuevo ADR).
