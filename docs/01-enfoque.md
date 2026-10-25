# 01 · Enfoque

## 1. El problema

En una aplicación de gestión típica, la mayor parte del esfuerzo de desarrollo no va a **lo que la aplicación debe hacer**, sino a **cómo se pinta y se cablea**: formularios, listados, validaciones repetidas en cliente y servidor, estados de carga, navegación, adaptaciones a cambios de diseño. Brooks distinguía entre **complejidad esencial** (la del problema: reglas, datos, flujos) y **complejidad accidental** (la de las herramientas y la implementación) [R1]. La construcción de interfaces de gestión es, en su mayor parte, complejidad accidental: muy parecida de una aplicación a otra, costosa de escribir y más costosa de mantener.

Además, el software útil cambia de forma continua: las leyes de Lehman establecen que un sistema que se usa debe modificarse continuamente o pierde utilidad, y que su complejidad crece salvo que se trabaje activamente en reducirla [R2]. Cada cambio funcional se traduce hoy en código de interfaz que hay que reescribir, probar y desplegar.

**Hipótesis de Eidos:** si las personas expresan con precisión *qué* quieren (funcional), *cómo debe verse y sentirse* (diseño), *con qué datos y reglas* (técnico) y *cómo se comprueba* (pruebas), un sistema de agentes puede **construir y mantener** la mayor parte de la interfaz, y el equipo humano puede dedicar su tiempo a la complejidad esencial y a la validación.

## 2. La propuesta en cinco ideas

1. **Las entradas son humanas y son la fuente de verdad.** Documento funcional, diseño, especificaciones técnicas y pruebas. El sistema no inventa requisitos ni pruebas: puede proponerlos, pero no entran sin aprobación.
2. **La interfaz es un artefacto derivado.** Igual que un binario se deriva del código fuente, las pantallas se derivan de las entradas. Se generan dentro de un vocabulario cerrado (catálogo de componentes), se verifican y se publican bloqueadas.
3. **El sistema construye; las personas definen y validan.** El desarrollador deja de codificar pantallas y pasa a especificar, revisar informes de conformidad y aprobar lo que la política marca como de su competencia.
4. **La plataforma pone las reglas de intervención.** Qué se automatiza, qué se escala a una persona, con qué evidencia y en qué plazo lo deciden políticas declaradas y auditables, no el criterio de cada momento.
5. **Genérico por construcción.** La plataforma no conoce ningún dominio. Funciones de aptitud automáticas lo comprueban en cada cambio, con un segundo dominio "testigo".

## 3. Roles y responsabilidades

| Actividad | Funcional | Diseño | Desarrollador | Equipo de IA | Sistema |
|---|---|---|---|---|---|
| Documento funcional (requisitos, criterios de aceptación) | **R/A** | C | C | I | Propone mejoras, señala ambigüedades |
| Sistema de diseño (tokens, catálogo, patrones, tono) | C | **R/A** | C | I | Valida coherencia |
| Especificaciones técnicas (datos, comandos, permisos, integraciones) | C | I | **R/A** | C | Valida integridad, propone migraciones |
| Pruebas de aceptación | **R** | I | **A** | I | Propone borradores; los ejecuta |
| Componentes manuales | I | C | **R/A** | I | Los integra en el catálogo |
| Plataforma (agentes, pipeline, guardián, modelos) | I | I | C | **R/A** | — |
| Construir y verificar pantallas | I | I | I | I | **R** |
| Aprobar publicación (según clase de riesgo) | C | C | **A** | I | Aprueba lo autorizado por política |
| Reparar pantallas | I | I | A (riesgo alto) | I | **R** |

R = responsable de hacerlo · A = aprueba/rinde cuentas · C = consultado · I = informado.

El desarrollador cambia de perfil: de **constructor de interfaces** a **ingeniero de especificaciones y garante de calidad**. Sigue escribiendo código donde aporta (componentes manuales, integraciones, reglas complejas), pero no código repetitivo de pantallas.

## 4. Fundamentos: qué dice la evidencia

### 4.1 Desarrollo dirigido por modelos (MDE): funciona, con condiciones

La idea de generar software a partir de modelos no es nueva: la *Model-Driven Architecture* de OMG [R3] y la ingeniería dirigida por modelos [R4] la formalizaron hace dos décadas. Los estudios empíricos en industria aportan las condiciones de éxito que adoptamos:

- Hutchinson et al. encontraron beneficios reales de productividad y mantenibilidad, pero ligados a **lenguajes específicos de dominio pequeños** y a factores organizativos, no a modelos genéricos de todo el sistema [R5].
- Whittle, Hutchinson y Rouncefield observaron que los casos de éxito usan MDE **para partes concretas del sistema**, conviven con código escrito a mano y fracasan cuando se pretende modelar todo [R6].

**Consecuencias para Eidos:** especificaciones con formato estrecho y validado (no prosa libre ni UML genérico); catálogo cerrado; y una **ruta manual de primera clase** para lo que no encaja (componentes propios registrados en el catálogo).

### 4.2 La novedad: generadores que entienden lenguaje natural, con salida restringida

Lo que hace viable hoy lo que MDE no conseguía es que el generador ya no es una plantilla rígida, sino un modelo de lenguaje capaz de interpretar intención y diseño. Pero un modelo no es determinista ni fiable por sí mismo. Tres técnicas lo hacen utilizable:

- **Decodificación restringida por esquema:** el servidor del modelo solo puede emitir JSON válido contra un esquema [R7]. Ollama y Azure OpenAI lo ofrecen hoy (salida estructurada).
- **UI declarativa sobre catálogo cerrado:** el modelo describe la interfaz como datos y el cliente solo pinta componentes de confianza. Es el núcleo de A2UI (Google) [R8], de json-render (Vercel) [R9] y del *server-driven UI* que usa Airbnb en producción [R10].
- **Bucle generar-evaluar:** el patrón *evaluator-optimizer* descrito por Anthropic para sistemas agénticos [R11]: un paso genera, otro evalúa con criterios claros y devuelve retroalimentación.

### 4.3 La corrección necesita un oráculo externo

Que un agente "se revise a sí mismo" no basta:

- Huang et al. muestran que los modelos **no se autocorrigen de forma fiable sin retroalimentación externa**; a veces empeoran la respuesta [R12].
- Olausson et al. concluyen que la autorreparación de código depende sobre todo de **la calidad de la retroalimentación** (p. ej. pruebas que fallan), no del modelo que repara [R13].
- Cuando la retroalimentación existe, el refinamiento iterativo sí mejora los resultados (Self-Refine [R14], Reflexion [R15]), y los agentes que reparan software se evalúan precisamente contra pruebas que deben pasar (SWE-bench [R16]).
- Usar un modelo como juez es útil para ordenar y detectar problemas, pero tiene **sesgos documentados**: posición, extensión y preferencia por respuestas propias [R17].

**Consecuencias:** en Eidos **no se repara sin una comprobación que falle** (prueba, regla del guardián, error en ejecución). El agente validador es **consultivo**; el oráculo son las pruebas deterministas escritas por personas.

### 4.4 Las especificaciones deben ser verificables y trazables

- La norma ISO/IEC/IEEE 29148 exige que los requisitos sean, entre otras cosas, **no ambiguos, verificables y trazables** [R18].
- La trazabilidad requisito → implementación → prueba es un problema clásico de la ingeniería de requisitos [R19]; aquí el sistema puede mantenerla automáticamente porque genera los artefactos intermedios.
- *Specification by Example* y BDD proponen que los criterios de aceptación sean **ejemplos ejecutables** con formato Dado/Cuando/Entonces [R20][R21]. Es el formato que adoptamos para las pruebas de aceptación.
- El **lenguaje ubicuo** de Domain-Driven Design [R22]: documento funcional, especificaciones y pantallas usan el mismo glosario; el sistema lo comprueba.

### 4.5 Supervisión humana: qué automatizar y cómo

- Parasuraman, Sheridan y Wickens proponen decidir el **nivel de automatización por tipo de función** (adquirir información, analizarla, decidir, actuar) y en función del riesgo [R23]. Es la base de nuestras clases de riesgo y niveles de autonomía.
- Bainbridge describió las **ironías de la automatización**: cuanto más se automatiza, más difícil es para la persona supervisar bien, porque pierde contexto y práctica [R24]. Por eso las intervenciones se diseñan con contexto, evidencia y alcance acotado, no como "aprobar en bloque".
- Las guías de interacción persona-IA de Microsoft piden dejar claro qué puede hacer el sistema, facilitar la corrección y explicar por qué hizo algo [R25].
- El marco de riesgos de IA del NIST [R26] y el artículo 14 del Reglamento europeo de IA [R27] exigen supervisión humana efectiva y trazabilidad en sistemas que toman decisiones. Aunque una aplicación de gestión interna no sea de alto riesgo, adoptar estas prácticas desde el principio es barato y evita rediseños.

### 4.6 Arquitectura para cambiar sin romper

- **Estado deseado y reconciliación:** los orquestadores de Google (Borg, Omega, Kubernetes) gestionan millones de cargas con un principio sencillo: el usuario declara el estado deseado y unos *controladores* reconcilian continuamente el estado real con él [R28]. GitOps aplica lo mismo con git como fuente de verdad. Eidos usa este patrón: el paquete de entradas es el estado deseado; los controladores de artefactos lo reconcilian.
- **Tubería de entrega con puertas de calidad** [R29] y métricas de entrega [R30]: cada cambio pasa por las mismas etapas automáticas antes de publicarse.
- **Funciones de aptitud** de las arquitecturas evolutivas [R31]: propiedades de la arquitectura comprobadas automáticamente en cada cambio. Las usamos para impedir que la plataforma se vuelva ad hoc.
- **Ocultación de información** [R32], **diseño por contrato** [R33] y **puertos y adaptadores** [R34]: la plataforma se comunica con modelos, bases de datos y renderizadores a través de contratos; cambiar de proveedor no toca el núcleo.
- **Deuda técnica en sistemas con aprendizaje automático** [R35] y **retos de ingeniería del ML** [R36]: el código de pegamento, las dependencias de datos no declaradas y los bucles de retroalimentación ocultos son el riesgo principal. Lo mitigamos con contratos explícitos, dependencias declaradas por artefacto y evaluación continua.

### 4.7 Tendencia actual: desarrollo dirigido por especificaciones con IA

En 2025 se consolidó el *spec-driven development* asistido por agentes: GitHub publicó Spec Kit, un conjunto de herramientas en el que la especificación y el plan, escritos y revisados por personas, guían a los agentes de código [R37]. Eidos comparte la idea de que **la especificación es el producto del trabajo humano**, pero va un paso más allá en un ámbito acotado: en lugar de generar código fuente que luego mantienen personas, genera **artefactos declarativos** que el propio sistema mantiene y verifica, dentro de un catálogo cerrado.

## 5. Qué no es Eidos

- **No es un sistema autónomo.** Las personas definen, aprueban lo que la política les asigna y pueden detener o revertir cualquier cosa.
- **No es low-code visual.** No hay editor de pantallas: se describe *qué* se necesita y el sistema decide *cómo* dentro del sistema de diseño.
- **No genera código fuente arbitrario.** Genera documentos declarativos validados. El código lo escriben personas (componentes manuales, integraciones) o se mantiene con el proceso habitual.
- **No sustituye a las pruebas.** Las ejecuta, informa y propone; no las escribe en nombre del equipo.
- **No pretende cubrir el 100 %.** Objetivo realista: la mayoría de pantallas de una aplicación de gestión ligera. El resto entra por la ruta manual sin salir de la arquitectura.

## 6. Riesgos y mitigaciones

| Riesgo | Mitigación | Dónde se aplica |
|---|---|---|
| La ambigüedad del documento funcional produce errores silenciosos | Especificación compilada intermedia + detección de ambigüedades + aprobación humana | Puerta G1, intervención H1 |
| El generador y el validador comparten sesgos | Pruebas deterministas como oráculo; juez solo consultivo | Puerta G4 |
| El sistema ajusta las pruebas para pasarlas | Las pruebas son entradas humanas; el sistema no puede modificarlas | Regla RP-03 |
| Reparaciones no solicitadas cambian lo aprobado | Sin oráculo no hay reparación; alcance limitado por clase | Política de reparación |
| Resultados no reproducibles | Artefactos bloqueados por versión; regeneración solo por cambio de dependencias | Ciclo de vida |
| Cambios en datos con pérdida irreversible | Migraciones propuestas, nunca aplicadas sin aprobación, copia y reversión | Intervención H4 |
| La plataforma se adapta a la primera aplicación | Funciones de aptitud + dominio testigo en CI | Doc. 04 |
| Supervisores que aprueban sin mirar | Intervenciones pequeñas, con evidencia y diferencias; muestreo de auditoría | Doc. 04 §5 |
| Dependencia de un proveedor de modelos | Perfiles de modelo + evaluación con al menos dos perfiles | ADR-09 |
| Datos personales enviados a modelos cloud | Minimización de datos en prompts; política por perfil | ADR-10 |

## 7. Cómo sabremos que funciona

| Indicador | Objetivo del piloto |
|---|---|
| % de pantallas del piloto construidas sin código humano | ≥ 80 % |
| % de pantallas válidas en la primera generación (por perfil) | ≥ 90 % |
| % de requisitos con trazabilidad completa (requisito → especificación → pantalla → prueba) | 100 % |
| Tiempo desde cambio funcional aprobado hasta publicación | < 1 día, sin escribir código de interfaz |
| Intervenciones humanas por cambio funcional | Mínimas y todas justificadas por política |
| Violaciones de funciones de aptitud | 0 |
| Datos personales en prompts a modelos cloud | 0 |
