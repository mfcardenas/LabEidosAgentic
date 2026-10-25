# 07 · Decisiones de arquitectura (ADR)

Formato breve de Nygard [R40]: contexto, decisión, consecuencias. Cada ADR se puede debatir y sustituir por otro; nunca se edita uno aceptado, se reemplaza.

| ADR | Estado | Título |
|---|---|---|
| 01 | Propuesta | Entradas humanas como fuente de verdad; artefactos derivados |
| 02 | Propuesta | Plano de control y plano de ejecución separados |
| 03 | Propuesta | Reconciliación con tipos de artefacto como punto de extensión |
| 04 | Propuesta | Catálogo en JSON Schema como fuente única |
| 05 | Propuesta | Documento de pantalla plano alineado con A2UI |
| 06 | Propuesta | Pruebas deterministas como oráculo; juez consultivo |
| 07 | Propuesta | Clases de riesgo y niveles de autonomía por política |
| 08 | Propuesta | Artefactos bloqueados y revalidación por dependencias |
| 09 | Propuesta | Perfiles de modelo y adaptadores |
| 10 | Propuesta | Minimización de datos en prompts |
| 11 | Propuesta | Python en servidor, TypeScript en cliente |
| 12 | Propuesta | Git y CI como columna vertebral del ciclo |
| 13 | Propuesta | Funciones de aptitud y dominio testigo |

---

### ADR-01 · Entradas humanas como fuente de verdad

**Contexto.** El sistema debe construir la interfaz, pero la responsabilidad de qué se construye es humana. Los modelos no son deterministas.
**Decisión.** Documento funcional, diseño, especificaciones técnicas y pruebas son entradas humanas versionadas. Todo lo demás es artefacto derivado con procedencia.
**Consecuencias.** + Responsabilidad clara, auditoría. + Regenerable. − Exige disciplina en la escritura de entradas (G0 la hace cumplir).
**Alternativas descartadas.** Que el sistema infiera requisitos del uso o de conversaciones: pierde trazabilidad y control.

### ADR-02 · Plano de control y plano de ejecución separados

**Contexto.** Generar con modelos es lento, costoso y variable; servir a usuarios debe ser rápido y estable.
**Decisión.** Los agentes trabajan en el plano de control; el plano de ejecución sirve artefactos publicados de forma determinista. La generación a demanda es una excepción acotada a clase baja.
**Consecuencias.** + Estabilidad y escalado del plano de ejecución. + El equipo de IA evoluciona los agentes sin afectar a producción. − Dos despliegues.
**Referencias.** Borg/Omega/Kubernetes [R28].

### ADR-03 · Reconciliación con tipos de artefacto

**Contexto.** Hay que evitar que cada necesidad nueva añada una ruta especial.
**Decisión.** Un único reconciliador; cada clase de salida es un `ArtifactKind` con la misma interfaz (dependencias, plan, generar, verificar, riesgo, reparar).
**Consecuencias.** + Extensible sin tocar el núcleo (F5). + Mismo control de calidad para todo. − Diseño inicial más abstracto.

### ADR-04 · Catálogo en JSON Schema como fuente única

**Contexto.** En el prototipo, el catálogo en prosa provocó salidas mal formadas (propiedades anidadas, enlaces como texto).
**Decisión.** Un esquema por componente con metadatos; de él se derivan prompt, salida estructurada, validación, documentación y tipos del cliente.
**Consecuencias.** + Coherencia por construcción. + Decodificación restringida [R7]. − Escribir esquemas cuesta más que prosa.
**Referencias.** json-render [R9], A2UI [R8].

### ADR-05 · Documento de pantalla plano alineado con A2UI

**Contexto.** Los árboles anidados son difíciles de generar por partes, validar y reparar localmente.
**Decisión.** Lista plana de componentes con `id`, enlaces JSON Pointer, acciones `function`/`command`.
**Consecuencias.** + Regiones, reparación localizada, compatibilidad futura con renderizadores A2UI. − Menos legible a simple vista (la consola lo muestra como árbol).

### ADR-06 · Pruebas deterministas como oráculo; juez consultivo

**Contexto.** La autocorrección sin retroalimentación externa no es fiable [R12][R13]; los jueces basados en modelo tienen sesgos [R17].
**Decisión.** Solo las pruebas (escritas o aprobadas por personas) y el guardián bloquean o aprueban. El juez puntúa y prioriza.
**Consecuencias.** + Calidad verificable. − Requiere que funcionales y desarrollador escriban pruebas (es parte de su nuevo rol).

### ADR-07 · Clases de riesgo y niveles de autonomía por política

**Contexto.** No todo merece la misma supervisión [R23]; la supervisión excesiva se vuelve rutinaria [R24].
**Decisión.** La clase se calcula a partir de la especificación; la autonomía y las intervenciones las fija una política versionada.
**Consecuencias.** + Supervisión proporcional y auditable. − Hay que calibrar las políticas con el uso.

### ADR-08 · Artefactos bloqueados y revalidación por dependencias

**Contexto.** Los modelos producen resultados distintos ante la misma entrada; los proveedores cambian modelos.
**Decisión.** Lo publicado es inmutable; solo se revalida si cambia una dependencia con huella; solo se regenera si la revalidación falla o por decisión registrada.
**Consecuencias.** + Reproducibilidad y estabilidad. + "Reparar antes de que se note". − Almacenamiento de versiones.

### ADR-09 · Perfiles de modelo y adaptadores

**Contexto.** Necesitamos modelos locales y cloud, y poder cambiarlos.
**Decisión.** Perfiles con capacidades y política de datos; adaptadores por proveedor (puertos y adaptadores [R34]); asignación por agente; evaluación con al menos dos perfiles (F10).
**Consecuencias.** + Sin dependencia de proveedor. − Mantener la batería de evaluación.

### ADR-10 · Minimización de datos en prompts

**Contexto.** En el prototipo, el intérprete recibía registros reales; con un perfil cloud eso exporta datos personales.
**Decisión.** Prompts con esquemas y ejemplos sintéticos; resolución de registros con herramientas en el servidor; perfiles externos nunca reciben datos reales (RP-07).
**Consecuencias.** + Privacidad. − El intérprete necesita herramientas de búsqueda.

### ADR-11 · Python en servidor, TypeScript en cliente

**Contexto.** El equipo de IA construye el backend; el cliente debe ser pequeño y estable.
**Decisión.** Python (FastAPI, Pydantic) en los dos planos; TypeScript en el renderizador y la consola. Frontera = contratos JSON Schema; los tipos del cliente se generan de ellos.
**Consecuencias.** + Ecosistema de IA y tipado de contratos. − Dos lenguajes (mitigado por los esquemas compartidos).
**Alternativa descartada.** TypeScript de extremo a extremo: válido técnicamente, pero no encaja con el equipo que mantiene el backend.

### ADR-12 · Git y CI como columna vertebral

**Contexto.** No queremos construir herramientas propias para revisión, versiones y permisos.
**Decisión.** Las entradas viven en git; cada solicitud de cambio ejecuta el plano de control en modo lote y publica el informe de conformidad; la fusión dispara la publicación.
**Consecuencias.** + Reutiliza revisión, historial y permisos existentes [R29]. − La consola debe integrarse con el flujo de git.

### ADR-13 · Funciones de aptitud y dominio testigo

**Contexto.** El riesgo de que la plataforma se adapte al primer dominio es alto.
**Decisión.** F1-F12 en el CI de plataforma, incluido un segundo dominio completo que debe pasar siempre.
**Consecuencias.** + Generalidad demostrada, no supuesta [R31]. − Mantener un dominio adicional.
